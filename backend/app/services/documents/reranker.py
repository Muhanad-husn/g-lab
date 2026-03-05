"""Cross-encoder reranking service.

Re-scores retrieved document chunks using a cross-encoder model for higher
relevance accuracy than bi-encoder (vector) retrieval alone.

The default model is ``cross-encoder/ms-marco-MiniLM-L-6-v2``, a lightweight
MS MARCO-trained cross-encoder with good precision/latency tradeoffs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import DocumentChunk

logger: Any = get_logger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_DEFAULT_TOP_K = 3


class RerankerService:
    """Re-rank a list of document chunks using a cross-encoder.

    Usage::

        svc = RerankerService(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
        reranked = await svc.rerank("who owns company X", chunks, top_k=3)
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rerank(
        self,
        query: str,
        chunks: list[DocumentChunk],
        top_k: int = _DEFAULT_TOP_K,
    ) -> list[DocumentChunk]:
        """Re-score *chunks* against *query* and return the top-k by new score.

        Args:
            query: Natural-language question used to score each chunk.
            chunks: Candidate chunks (from vector search) to be re-ranked.
            top_k: Maximum number of chunks to return after re-ranking.

        Returns:
            At most *top_k* chunks sorted by descending cross-encoder score.
            If *chunks* is empty, returns an empty list immediately without
            loading the model.  If ``len(chunks) <= top_k`` all chunks are
            returned (but still re-scored and sorted).
        """
        if not chunks:
            return []

        model = self._load_model()
        pairs = [(query, chunk.text) for chunk in chunks]
        scores: list[float] = await asyncio.to_thread(
            lambda: list(map(float, model.predict(pairs)))
        )

        scored = sorted(
            zip(scores, chunks, strict=True),
            key=lambda x: x[0],
            reverse=True,
        )
        result = [chunk for _, chunk in scored[:top_k]]

        logger.info(
            "reranker_complete",
            model=self._model_name,
            input_count=len(chunks),
            top_k=top_k,
            returned=len(result),
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> Any:
        """Lazily load and cache the CrossEncoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("reranker_model_loading", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("reranker_model_ready", model=self._model_name)
        return self._model
