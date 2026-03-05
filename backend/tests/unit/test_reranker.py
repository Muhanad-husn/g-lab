"""Unit tests for RerankerService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import ChunkMetadata, DocumentChunk
from app.services.documents.reranker import RerankerService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(
    chunk_id: str,
    text: str,
    similarity: float = 0.5,
    doc_id: str = "doc-1",
    library_id: str = "lib-abc",
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            document_id=doc_id,
            library_id=library_id,
            page_number=1,
            section_heading=None,
            chunk_index=0,
            parse_tier="high",
        ),
        similarity_score=similarity,
    )


def _make_reranker(scores: list[float]) -> RerankerService:
    """Return a RerankerService with a mocked CrossEncoder that returns *scores*."""
    svc = RerankerService(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    mock_model = MagicMock()
    mock_model.predict.return_value = scores
    svc._model = mock_model  # inject pre-loaded model
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_orders_by_score_descending() -> None:
    """Chunks should be returned in descending cross-encoder score order."""
    chunks = [
        _chunk("c-1", "low relevance text"),
        _chunk("c-2", "highly relevant text about the query"),
        _chunk("c-3", "somewhat relevant content"),
    ]
    # CrossEncoder assigns c-2 the highest score
    svc = _make_reranker(scores=[0.1, 0.9, 0.5])

    result = await svc.rerank("test query", chunks, top_k=3)

    assert len(result) == 3
    assert result[0].id == "c-2"  # highest score
    assert result[1].id == "c-3"  # second
    assert result[2].id == "c-1"  # lowest


@pytest.mark.asyncio
async def test_rerank_returns_top_k() -> None:
    """Only the top-k chunks should be returned."""
    chunks = [_chunk(f"c-{i}", f"text {i}") for i in range(5)]
    svc = _make_reranker(scores=[0.1, 0.4, 0.9, 0.2, 0.7])

    result = await svc.rerank("query", chunks, top_k=2)

    assert len(result) == 2
    assert result[0].id == "c-2"  # score 0.9
    assert result[1].id == "c-4"  # score 0.7


@pytest.mark.asyncio
async def test_rerank_fewer_chunks_than_top_k_returns_all() -> None:
    """When fewer chunks than top_k exist, all should be returned."""
    chunks = [_chunk("c-1", "text one"), _chunk("c-2", "text two")]
    svc = _make_reranker(scores=[0.8, 0.3])

    result = await svc.rerank("query", chunks, top_k=10)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_rerank_empty_input_returns_empty() -> None:
    """Empty chunk list should return immediately without loading the model."""
    svc = RerankerService()
    # _model is None — would fail if model.predict were called
    result = await svc.rerank("query", [], top_k=3)

    assert result == []
    assert svc._model is None  # model not loaded


@pytest.mark.asyncio
async def test_rerank_calls_predict_with_correct_pairs() -> None:
    """CrossEncoder.predict must receive (query, chunk_text) pairs."""
    chunks = [_chunk("c-1", "alpha"), _chunk("c-2", "beta")]
    svc = _make_reranker(scores=[0.6, 0.4])

    await svc.rerank("my question", chunks, top_k=2)

    svc._model.predict.assert_called_once_with(
        [("my question", "alpha"), ("my question", "beta")]
    )


@pytest.mark.asyncio
async def test_rerank_lazy_loads_model_on_first_call() -> None:
    """Model should be loaded only on the first rerank call."""
    svc = RerankerService(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert svc._model is None

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5]

    chunks = [_chunk("c-1", "text")]
    with patch(
        "app.services.documents.reranker.RerankerService._load_model",
        return_value=mock_model,
    ) as mock_load:
        await svc.rerank("query", chunks, top_k=1)
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_rerank_single_chunk_returned_regardless_of_top_k() -> None:
    """A single chunk should always be returned (top_k >= 1)."""
    chunks = [_chunk("c-only", "only chunk")]
    svc = _make_reranker(scores=[0.77])

    result = await svc.rerank("query", chunks, top_k=5)

    assert len(result) == 1
    assert result[0].id == "c-only"
