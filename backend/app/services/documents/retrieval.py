"""Document vector search service.

Wraps ChromaDB query + EmbeddingService to return ranked DocumentChunk
objects for a given natural-language query against a library collection.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.schemas import ChunkMetadata, DocumentChunk
from app.services.documents.chromadb_client import ChromaDBClient
from app.services.documents.embeddings import EmbeddingService

logger: Any = get_logger(__name__)

_DEFAULT_TOP_K = 5


class DocumentRetrievalService:
    """Retrieve the most relevant document chunks for a query.

    Usage::

        svc = DocumentRetrievalService(chroma_client, embedding_svc)
        chunks = await svc.retrieve("who owns company X", library_id="lib-abc", top_k=5)
    """

    def __init__(
        self,
        chroma_client: ChromaDBClient,
        embedding_service: EmbeddingService,
    ) -> None:
        self._chroma = chroma_client
        self._embeddings = embedding_service

    async def retrieve(
        self,
        query: str,
        library_id: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> list[DocumentChunk]:
        """Embed *query* and return the top-k most similar chunks from *library_id*.

        Args:
            query: Natural-language question or search phrase.
            library_id: ChromaDB collection name (same as SQLite library id).
            top_k: Maximum number of chunks to return.

        Returns:
            List of :class:`DocumentChunk` objects ordered by descending
            similarity (closest first).  Returns an empty list when the
            collection is empty or ChromaDB returns no results.
        """
        query_embedding = await self._embeddings.embed_query(query)

        result = await self._chroma.query(
            collection=library_id,
            query_embedding=query_embedding,
            n_results=top_k,
        )

        chunks = _map_query_result(result, library_id)
        logger.info(
            "document_retrieval_complete",
            library_id=library_id,
            top_k=top_k,
            returned=len(chunks),
        )
        return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _map_query_result(result: dict[str, Any], library_id: str) -> list[DocumentChunk]:
    """Convert a raw ChromaDB QueryResult dict to DocumentChunk objects.

    ChromaDB returns batched results with an outer list per query embedding.
    We always issue single-embedding queries, so we index ``[0]`` throughout.
    """
    ids: list[str] = (result.get("ids") or [[]])[0]
    if not ids:
        return []

    documents: list[str] = (result.get("documents") or [[]])[0]
    metadatas: list[dict[str, Any]] = (result.get("metadatas") or [[]])[0]
    distances: list[float] = (result.get("distances") or [[]])[0]

    chunks: list[DocumentChunk] = []
    for idx, chunk_id in enumerate(ids):
        meta: dict[str, Any] = metadatas[idx] if idx < len(metadatas) else {}
        text: str = documents[idx] if idx < len(documents) else ""
        distance: float = distances[idx] if idx < len(distances) else 1.0
        # ChromaDB L2 distance: 0 = identical; convert to similarity ∈ [0, 1]
        similarity: float = max(0.0, 1.0 - distance)

        chunk = DocumentChunk(
            id=chunk_id,
            text=text,
            metadata=ChunkMetadata(
                document_id=meta.get("document_id", ""),
                library_id=meta.get("library_id", library_id),
                page_number=meta.get("page_number"),
                section_heading=meta.get("section_heading"),
                chunk_index=int(meta.get("chunk_index", idx)),
                parse_tier=meta.get("parse_tier", "basic"),
            ),
            similarity_score=similarity,
        )
        chunks.append(chunk)

    return chunks
