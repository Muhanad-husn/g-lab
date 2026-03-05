"""Unit tests for ChromaDBClient (mocked chromadb)."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject a mock chromadb module so the module under test can be imported
# without the real chromadb package installed.
# ---------------------------------------------------------------------------
if "chromadb" not in sys.modules:
    sys.modules["chromadb"] = MagicMock()

from app.services.documents.chromadb_client import ChromaDBClient, ChromaDBError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collection_mock(**overrides: Any) -> AsyncMock:
    """Return an AsyncMock that looks like a chromadb Collection."""
    col = AsyncMock()
    col.add = AsyncMock()
    col.query = AsyncMock(
        return_value={
            "ids": [["id1"]],
            "distances": [[0.1]],
            "documents": [["doc text"]],
            "metadatas": [[{"source": "test"}]],
        }
    )
    col.delete = AsyncMock()
    col.count = AsyncMock(return_value=42)
    for key, val in overrides.items():
        setattr(col, key, val)
    return col


def _make_chroma_client_mock(collection: AsyncMock | None = None) -> AsyncMock:
    """Return an AsyncMock that looks like chromadb.AsyncClientAPI."""
    col = collection or _make_collection_mock()
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=col)
    client.delete_collection = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# connect / close / is_connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_success() -> None:
    mock_client = _make_chroma_client_mock()

    with patch.dict(sys.modules, {"chromadb": MagicMock(AsyncHttpClient=AsyncMock(return_value=mock_client))}):
        client = ChromaDBClient()
        assert not client.is_connected()
        await client.connect(host="localhost", port=8000)
        assert client.is_connected()
        await client.close()
        assert not client.is_connected()


@pytest.mark.asyncio
async def test_connect_failure_raises_chromadb_error() -> None:
    with patch.dict(
        sys.modules,
        {"chromadb": MagicMock(AsyncHttpClient=AsyncMock(side_effect=ConnectionRefusedError("refused")))},
    ):
        client = ChromaDBClient()
        with pytest.raises(ChromaDBError, match="Failed to connect"):
            await client.connect(host="badhost", port=9999)
        assert not client.is_connected()


@pytest.mark.asyncio
async def test_require_client_raises_when_disconnected() -> None:
    client = ChromaDBClient()
    with pytest.raises(ChromaDBError, match="not connected"):
        await client.create_collection("test")


# ---------------------------------------------------------------------------
# Collection CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_collection() -> None:
    mock_client = _make_chroma_client_mock()
    client = ChromaDBClient()
    client._client = mock_client  # inject directly
    client._connected = True

    await client.create_collection("my-library")
    mock_client.get_or_create_collection.assert_called_once_with(name="my-library")


@pytest.mark.asyncio
async def test_delete_collection_success() -> None:
    mock_client = _make_chroma_client_mock()
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    await client.delete_collection("my-library")
    mock_client.delete_collection.assert_called_once_with(name="my-library")


@pytest.mark.asyncio
async def test_delete_collection_missing_does_not_raise() -> None:
    mock_client = _make_chroma_client_mock()
    mock_client.delete_collection = AsyncMock(side_effect=Exception("not found"))
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    # Should not propagate the exception
    await client.delete_collection("missing-library")


# ---------------------------------------------------------------------------
# add_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_documents() -> None:
    col = _make_collection_mock()
    mock_client = _make_chroma_client_mock(collection=col)
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    await client.add_documents(
        collection="lib",
        ids=["c1", "c2"],
        embeddings=[[0.1] * 384, [0.2] * 384],
        metadatas=[{"doc_id": "d1"}, {"doc_id": "d1"}],
        documents=["chunk one", "chunk two"],
    )

    col.add.assert_called_once_with(
        ids=["c1", "c2"],
        embeddings=[[0.1] * 384, [0.2] * 384],
        metadatas=[{"doc_id": "d1"}, {"doc_id": "d1"}],
        documents=["chunk one", "chunk two"],
    )


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_returns_results() -> None:
    col = _make_collection_mock()
    mock_client = _make_chroma_client_mock(collection=col)
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    result = await client.query(
        collection="lib",
        query_embedding=[0.5] * 384,
        n_results=3,
    )

    col.query.assert_called_once_with(
        query_embeddings=[[0.5] * 384],
        n_results=3,
    )
    assert result["ids"] == [["id1"]]
    assert result["distances"] == [[0.1]]


@pytest.mark.asyncio
async def test_query_with_where_filter() -> None:
    col = _make_collection_mock()
    mock_client = _make_chroma_client_mock(collection=col)
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    await client.query(
        collection="lib",
        query_embedding=[0.1] * 384,
        n_results=5,
        where_filter={"doc_id": {"$eq": "d1"}},
    )

    col.query.assert_called_once_with(
        query_embeddings=[[0.1] * 384],
        n_results=5,
        where={"doc_id": {"$eq": "d1"}},
    )


# ---------------------------------------------------------------------------
# delete_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_documents() -> None:
    col = _make_collection_mock()
    mock_client = _make_chroma_client_mock(collection=col)
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    await client.delete_documents(collection="lib", ids=["c1", "c2"])
    col.delete.assert_called_once_with(ids=["c1", "c2"])


# ---------------------------------------------------------------------------
# get_collection_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collection_count() -> None:
    col = _make_collection_mock()
    mock_client = _make_chroma_client_mock(collection=col)
    client = ChromaDBClient()
    client._client = mock_client
    client._connected = True

    count = await client.get_collection_count("lib")
    assert count == 42
    col.count.assert_called_once()
