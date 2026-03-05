"""Copilot document retrieval role.

Wraps DocumentRetrievalService + RerankerService for use inside the copilot
pipeline.  Called when the router sets ``needs_docs=True`` and a document
library is attached to the current session.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.schemas import DocumentChunk, EvidenceSource, RouterIntent

logger: Any = get_logger(__name__)


class DocumentRetrievalRole:
    """Retrieve and rerank document chunks as part of the copilot pipeline.

    Usage::

        role = DocumentRetrievalRole(retrieval_svc, reranker_svc)
        chunks, sources = await role.retrieve(
            intent=intent,
            library_id="lib-abc",
            top_k=5,
            reranker_top_k=3,
        )
    """

    def __init__(self, retrieval_service: Any, reranker_service: Any) -> None:
        self._retrieval = retrieval_service
        self._reranker = reranker_service

    async def retrieve(
        self,
        intent: RouterIntent,
        library_id: str | None,
        top_k: int = 5,
        reranker_top_k: int = 3,
    ) -> tuple[list[DocumentChunk], list[EvidenceSource]]:
        """Retrieve and rerank document chunks for the given intent.

        Returns an empty tuple when skipped (``needs_docs=False`` or no
        library attached).

        Args:
            intent: Routing decision from RouterService.
            library_id: ID of the attached library, or None.
            top_k: Number of chunks to fetch from ChromaDB.
            reranker_top_k: Number of chunks to keep after reranking.

        Returns:
            ``(chunks, evidence_sources)`` — both empty when skipped.
        """
        if not intent.needs_docs:
            logger.debug("doc_retrieval_skipped", reason="needs_docs=False")
            return [], []

        if not library_id:
            logger.debug("doc_retrieval_skipped", reason="no_library_attached")
            return [], []

        query = intent.doc_query or ""
        if not query:
            logger.debug("doc_retrieval_skipped", reason="empty_doc_query")
            return [], []

        raw_chunks = await self._retrieval.retrieve(
            query=query,
            library_id=library_id,
            top_k=top_k,
        )

        reranked = await self._reranker.rerank(
            query=query,
            chunks=raw_chunks,
            top_k=reranker_top_k,
        )

        evidence_sources = _chunks_to_evidence(reranked)
        logger.info(
            "doc_retrieval_complete",
            library_id=library_id,
            raw_count=len(raw_chunks),
            reranked_count=len(reranked),
        )
        return reranked, evidence_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunks_to_evidence(chunks: list[DocumentChunk]) -> list[EvidenceSource]:
    """Convert DocumentChunk objects to EvidenceSource records."""
    sources: list[EvidenceSource] = []
    for chunk in chunks:
        meta = chunk.metadata
        content_parts: list[str] = []
        if meta.section_heading:
            content_parts.append(f"[{meta.section_heading}]")
        if meta.page_number is not None:
            content_parts.append(f"p.{meta.page_number}")
        content_parts.append(chunk.text[:200])
        sources.append(
            EvidenceSource(
                type="doc_chunk",
                id=chunk.id,
                content=" ".join(content_parts),
            )
        )
    return sources
