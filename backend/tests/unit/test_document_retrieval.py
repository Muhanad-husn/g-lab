"""Unit tests for DocumentRetrievalService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.documents.retrieval import DocumentRetrievalService, _map_query_result


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_chroma_result(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    distances: list[float],
) -> dict:
    """Build a ChromaDB-style query result dict (batched outer list)."""
    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
        "distances": [distances],
    }


def _meta(
    doc_id: str = "doc-1",
    library_id: str = "lib-abc",
    page: int | None = 1,
    heading: str | None = "Intro",
    chunk_index: int = 0,
    parse_tier: str = "high",
) -> dict:
    return {
        "document_id": doc_id,
        "library_id": library_id,
        "page_number": page,
        "section_heading": heading,
        "chunk_index": chunk_index,
        "parse_tier": parse_tier,
    }


@pytest.fixture()
def mock_chroma() -> AsyncMock:
    client = AsyncMock()
    client.query = AsyncMock()
    return client


@pytest.fixture()
def mock_embeddings() -> AsyncMock:
    svc = AsyncMock()
    svc.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return svc


@pytest.fixture()
def retrieval_svc(mock_chroma: AsyncMock, mock_embeddings: AsyncMock) -> DocumentRetrievalService:
    return DocumentRetrievalService(mock_chroma, mock_embeddings)


# ---------------------------------------------------------------------------
# Tests: retrieve()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_top_k_chunks(
    retrieval_svc: DocumentRetrievalService,
    mock_chroma: AsyncMock,
    mock_embeddings: AsyncMock,
) -> None:
    mock_chroma.query.return_value = _make_chroma_result(
        ids=["c-1", "c-2"],
        documents=["First chunk text.", "Second chunk text."],
        metadatas=[_meta(chunk_index=0), _meta(chunk_index=1)],
        distances=[0.1, 0.3],
    )

    chunks = await retrieval_svc.retrieve("who owns company X", library_id="lib-abc", top_k=5)

    assert len(chunks) == 2
    # Embedding was called with the query
    mock_embeddings.embed_query.assert_awaited_once_with("who owns company X")
    # ChromaDB was queried with the embedding
    mock_chroma.query.assert_awaited_once_with(
        collection="lib-abc",
        query_embedding=[0.1, 0.2, 0.3],
        n_results=5,
    )


@pytest.mark.asyncio
async def test_retrieve_chunks_ordered_closest_first(
    retrieval_svc: DocumentRetrievalService,
    mock_chroma: AsyncMock,
) -> None:
    # ChromaDB already returns results in distance order (ascending)
    mock_chroma.query.return_value = _make_chroma_result(
        ids=["c-1", "c-2", "c-3"],
        documents=["A", "B", "C"],
        metadatas=[_meta(chunk_index=0), _meta(chunk_index=1), _meta(chunk_index=2)],
        distances=[0.05, 0.4, 0.8],
    )

    chunks = await retrieval_svc.retrieve("query", library_id="lib-abc")

    # similarity = 1 - distance; first chunk should be highest similarity
    assert chunks[0].similarity_score > chunks[1].similarity_score  # type: ignore[operator]
    assert chunks[1].similarity_score > chunks[2].similarity_score  # type: ignore[operator]


@pytest.mark.asyncio
async def test_retrieve_empty_collection_returns_empty(
    retrieval_svc: DocumentRetrievalService,
    mock_chroma: AsyncMock,
) -> None:
    mock_chroma.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    chunks = await retrieval_svc.retrieve("query", library_id="lib-abc")

    assert chunks == []


@pytest.mark.asyncio
async def test_retrieve_metadata_mapped_correctly(
    retrieval_svc: DocumentRetrievalService,
    mock_chroma: AsyncMock,
) -> None:
    mock_chroma.query.return_value = _make_chroma_result(
        ids=["chunk-99"],
        documents=["Some text here."],
        metadatas=[
            _meta(
                doc_id="doc-42",
                library_id="lib-xyz",
                page=7,
                heading="Section 3",
                chunk_index=12,
                parse_tier="standard",
            )
        ],
        distances=[0.2],
    )

    chunks = await retrieval_svc.retrieve("query", library_id="lib-xyz")

    assert len(chunks) == 1
    c = chunks[0]
    assert c.id == "chunk-99"
    assert c.text == "Some text here."
    assert c.metadata.document_id == "doc-42"
    assert c.metadata.library_id == "lib-xyz"
    assert c.metadata.page_number == 7
    assert c.metadata.section_heading == "Section 3"
    assert c.metadata.chunk_index == 12
    assert c.metadata.parse_tier == "standard"
    assert c.similarity_score == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_retrieve_similarity_clamped_to_zero(
    retrieval_svc: DocumentRetrievalService,
    mock_chroma: AsyncMock,
) -> None:
    """Distance > 1.0 should clamp similarity to 0 rather than going negative."""
    mock_chroma.query.return_value = _make_chroma_result(
        ids=["c-1"],
        documents=["text"],
        metadatas=[_meta()],
        distances=[1.5],
    )

    chunks = await retrieval_svc.retrieve("query", library_id="lib-abc")

    assert chunks[0].similarity_score == 0.0


# ---------------------------------------------------------------------------
# Tests: _map_query_result() helper
# ---------------------------------------------------------------------------


def test_map_query_result_empty_ids() -> None:
    result = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    assert _map_query_result(result, "lib-abc") == []


def test_map_query_result_missing_keys_uses_defaults() -> None:
    """Missing metadata keys fall back to sensible defaults."""
    result = _make_chroma_result(
        ids=["c-1"],
        documents=["text"],
        metadatas=[{}],  # empty metadata
        distances=[0.0],
    )
    chunks = _map_query_result(result, "lib-fallback")
    assert len(chunks) == 1
    meta = chunks[0].metadata
    assert meta.library_id == "lib-fallback"
    assert meta.document_id == ""
    assert meta.page_number is None
    assert meta.section_heading is None
    assert meta.chunk_index == 0
    assert meta.parse_tier == "basic"


def test_map_query_result_none_outer_lists() -> None:
    """None values for result keys should produce empty output."""
    result: dict = {"ids": None, "documents": None, "metadatas": None, "distances": None}
    assert _map_query_result(result, "lib-abc") == []
