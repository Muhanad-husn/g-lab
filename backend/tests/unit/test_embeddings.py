"""Unit tests for EmbeddingService (mocked sentence-transformers)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject a mock sentence_transformers module so the module under test can be
# imported without the real package (which requires PyTorch) installed.
# ---------------------------------------------------------------------------
if "sentence_transformers" not in sys.modules:
    sys.modules["sentence_transformers"] = MagicMock()

from app.services.documents.embeddings import EmbeddingService  # noqa: E402

_DIMS = 384


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_mock(batch_size: int = 1) -> MagicMock:
    """Return a mock SentenceTransformer whose .encode() yields float lists."""
    model = MagicMock()
    model.encode.return_value = [[float(i) / 100 for i in range(_DIMS)] for _ in range(batch_size)]
    return model


# ---------------------------------------------------------------------------
# embed()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_returns_correct_dims() -> None:
    mock_model = _make_model_mock(batch_size=1)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService()
        result = await svc.embed(["hello world"])

    assert len(result) == 1
    assert len(result[0]) == _DIMS
    assert all(isinstance(v, float) for v in result[0])


@pytest.mark.asyncio
async def test_embed_batch() -> None:
    texts = ["doc one", "doc two", "doc three"]
    mock_model = _make_model_mock(batch_size=3)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService()
        result = await svc.embed(texts)

    assert len(result) == 3
    for vec in result:
        assert len(vec) == _DIMS
    mock_model.encode.assert_called_once_with(texts)


@pytest.mark.asyncio
async def test_embed_empty_returns_empty() -> None:
    svc = EmbeddingService()
    result = await svc.embed([])
    assert result == []


# ---------------------------------------------------------------------------
# embed_query()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_query_returns_single_vector() -> None:
    mock_model = _make_model_mock(batch_size=1)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService()
        vec = await svc.embed_query("search term")

    assert len(vec) == _DIMS
    assert isinstance(vec, list)
    assert all(isinstance(v, float) for v in vec)


# ---------------------------------------------------------------------------
# Lazy loading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_loaded_lazily() -> None:
    """Model should not be loaded until embed() is first called."""
    mock_model = _make_model_mock(batch_size=1)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService(model_name="all-MiniLM-L6-v2")
        assert svc._model is None  # not loaded yet

        await svc.embed(["test"])

        mock_st.SentenceTransformer.assert_called_once_with("all-MiniLM-L6-v2")
        assert svc._model is not None


@pytest.mark.asyncio
async def test_model_cached_on_second_call() -> None:
    """SentenceTransformer constructor should only be called once."""
    mock_model = _make_model_mock(batch_size=1)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService()
        await svc.embed(["first"])
        await svc.embed(["second"])

    assert mock_st.SentenceTransformer.call_count == 1


# ---------------------------------------------------------------------------
# Custom model name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_model_name() -> None:
    mock_model = _make_model_mock(batch_size=1)
    mock_st = MagicMock(SentenceTransformer=MagicMock(return_value=mock_model))

    with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
        svc = EmbeddingService(model_name="custom-model-v1")
        await svc.embed_query("x")

    mock_st.SentenceTransformer.assert_called_once_with("custom-model-v1")
