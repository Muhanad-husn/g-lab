"""Async ChromaDB HTTP client wrapper for document vector storage.

Wraps chromadb.AsyncHttpClient with a stable interface for collection
management, document ingestion, similarity search, and deletion.
The underlying chromadb import is deferred to connect() so the module
can be imported even when the chromadb package is not yet installed.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger: Any = get_logger(__name__)

_NOT_CONNECTED = "ChromaDB client is not connected. Call connect() first."


class ChromaDBError(Exception):
    """Raised on ChromaDB client errors."""


class ChromaDBClient:
    """Async wrapper around chromadb.AsyncHttpClient.

    Usage::

        client = ChromaDBClient()
        await client.connect(host="chromadb", port=8000)
        await client.create_collection("library-abc")
        await client.add_documents(
            collection="library-abc",
            ids=["chunk-1"],
            embeddings=[[0.1, 0.2, ...]],
            metadatas=[{"doc_id": "doc-1", "page": 1}],
            documents=["The quick brown fox..."],
        )
        results = await client.query(
            collection="library-abc",
            query_embedding=[0.1, 0.2, ...],
            n_results=5,
        )
        await client.close()
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, host: str, port: int) -> None:
        """Connect to a running ChromaDB HTTP server.

        Raises:
            ChromaDBError: If the connection attempt fails.
        """
        try:
            import chromadb

            self._client = await chromadb.AsyncHttpClient(host=host, port=port)
            self._connected = True
            logger.info("chromadb_connected", host=host, port=port)
        except ChromaDBError:
            raise
        except Exception as exc:
            self._connected = False
            raise ChromaDBError(
                f"Failed to connect to ChromaDB at {host}:{port}: {exc}"
            ) from exc

    async def close(self) -> None:
        """Release the ChromaDB client handle."""
        self._client = None
        self._connected = False
        logger.info("chromadb_closed")

    def is_connected(self) -> bool:
        """Return True when the client is ready to serve requests."""
        return self._connected and self._client is not None

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def create_collection(self, name: str) -> None:
        """Create a collection if it does not already exist (idempotent)."""
        client = self._require_client()
        await client.get_or_create_collection(name=name)
        logger.info("chromadb_collection_created", name=name)

    async def delete_collection(self, name: str) -> None:
        """Delete a collection.  Silently ignores missing collections."""
        client = self._require_client()
        try:
            await client.delete_collection(name=name)
            logger.info("chromadb_collection_deleted", name=name)
        except Exception as exc:
            logger.warning(
                "chromadb_collection_delete_failed", name=name, error=str(exc)
            )

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    async def add_documents(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        documents: list[str],
    ) -> None:
        """Add documents with pre-computed embeddings to a collection."""
        client = self._require_client()
        col = await client.get_or_create_collection(name=collection)
        await col.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        logger.info("chromadb_documents_added", collection=collection, count=len(ids))

    async def query(
        self,
        collection: str,
        query_embedding: list[float],
        n_results: int,
        where_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query a collection by embedding similarity.

        Returns the raw ChromaDB QueryResult dict with keys:
        ``ids``, ``distances``, ``documents``, ``metadatas``.
        All value lists have an outer batch dimension (one item per
        query embedding); callers should index ``result["ids"][0]``.
        """
        client = self._require_client()
        col = await client.get_or_create_collection(name=collection)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where_filter:
            kwargs["where"] = where_filter
        result: dict[str, Any] = await col.query(**kwargs)
        return result

    async def delete_documents(self, collection: str, ids: list[str]) -> None:
        """Delete specific documents from a collection by ID."""
        client = self._require_client()
        col = await client.get_or_create_collection(name=collection)
        await col.delete(ids=ids)
        logger.info("chromadb_documents_deleted", collection=collection, count=len(ids))

    async def get_collection_count(self, collection: str) -> int:
        """Return the number of embeddings stored in a collection."""
        client = self._require_client()
        col = await client.get_or_create_collection(name=collection)
        count: int = await col.count()
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> Any:
        if self._client is None:
            raise ChromaDBError(_NOT_CONNECTED)
        return self._client
