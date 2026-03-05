"""Unit tests for DocumentRetrievalRole."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.schemas import ChunkMetadata, DocumentChunk, RouterIntent
from app.services.copilot.document_retrieval import DocumentRetrievalRole


def _make_chunk(chunk_id: str, text: str = "sample text") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            document_id="doc-1",
            library_id="lib-1",
            page_number=1,
            section_heading="Introduction",
            chunk_index=0,
            parse_tier="standard",
        ),
        similarity_score=0.85,
    )


@pytest.fixture()
def retrieval_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.retrieve = AsyncMock(return_value=[_make_chunk("c1"), _make_chunk("c2")])
    return svc


@pytest.fixture()
def reranker_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.rerank = AsyncMock(return_value=[_make_chunk("c1")])
    return svc


@pytest.fixture()
def role(retrieval_svc: AsyncMock, reranker_svc: AsyncMock) -> DocumentRetrievalRole:
    return DocumentRetrievalRole(retrieval_svc, reranker_svc)


# ---------------------------------------------------------------------------
# needs_docs=True + library_id provided → retrieval + rerank → evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_happy_path(
    role: DocumentRetrievalRole,
    retrieval_svc: AsyncMock,
    reranker_svc: AsyncMock,
) -> None:
    intent = RouterIntent(
        needs_graph=False,
        needs_docs=True,
        doc_query="ownership structure",
    )
    chunks, sources = await role.retrieve(
        intent=intent,
        library_id="lib-1",
        top_k=5,
        reranker_top_k=3,
    )

    retrieval_svc.retrieve.assert_awaited_once_with(
        query="ownership structure",
        library_id="lib-1",
        top_k=5,
    )
    reranker_svc.rerank.assert_awaited_once()

    assert len(chunks) == 1  # reranker returned 1
    assert chunks[0].id == "c1"
    assert len(sources) == 1
    assert sources[0].type == "doc_chunk"
    assert sources[0].id == "c1"


# ---------------------------------------------------------------------------
# needs_docs=False → skipped entirely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_skipped_needs_docs_false(
    role: DocumentRetrievalRole,
    retrieval_svc: AsyncMock,
    reranker_svc: AsyncMock,
) -> None:
    intent = RouterIntent(needs_graph=True, needs_docs=False)
    chunks, sources = await role.retrieve(intent=intent, library_id="lib-1")

    retrieval_svc.retrieve.assert_not_called()
    reranker_svc.rerank.assert_not_called()
    assert chunks == []
    assert sources == []


# ---------------------------------------------------------------------------
# No library attached → skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_skipped_no_library(
    role: DocumentRetrievalRole,
    retrieval_svc: AsyncMock,
) -> None:
    intent = RouterIntent(needs_docs=True, doc_query="query")
    chunks, sources = await role.retrieve(intent=intent, library_id=None)

    retrieval_svc.retrieve.assert_not_called()
    assert chunks == []
    assert sources == []


# ---------------------------------------------------------------------------
# Empty doc_query → skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_skipped_empty_doc_query(
    role: DocumentRetrievalRole,
    retrieval_svc: AsyncMock,
) -> None:
    intent = RouterIntent(needs_docs=True, doc_query=None)
    chunks, sources = await role.retrieve(intent=intent, library_id="lib-1")

    retrieval_svc.retrieve.assert_not_called()
    assert chunks == []


# ---------------------------------------------------------------------------
# Evidence content includes section heading and page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_content_format(
    retrieval_svc: AsyncMock,
    reranker_svc: AsyncMock,
) -> None:
    chunk = _make_chunk("c99", text="This is important evidence.")
    retrieval_svc.retrieve = AsyncMock(return_value=[chunk])
    reranker_svc.rerank = AsyncMock(return_value=[chunk])

    role = DocumentRetrievalRole(retrieval_svc, reranker_svc)
    intent = RouterIntent(needs_docs=True, doc_query="test")
    _, sources = await role.retrieve(intent=intent, library_id="lib-1")

    assert len(sources) == 1
    src = sources[0]
    assert "Introduction" in src.content  # section_heading
    assert "p.1" in src.content  # page_number
    assert "This is important evidence." in src.content
