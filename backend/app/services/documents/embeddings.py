"""Embedding service using sentence-transformers.

Provides async wrappers for batch and single-query embedding via
``all-MiniLM-L6-v2`` (384 dimensions) by default.  The underlying
SentenceTransformer model is loaded lazily on first use so application
startup is not delayed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger

logger: Any = get_logger(__name__)

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Async text-to-vector embedding backed by sentence-transformers.

    The model is loaded from disk (or downloaded) on the first call to
    :meth:`embed` or :meth:`embed_query`.  Subsequent calls reuse the
    cached model instance.

    Usage::

        svc = EmbeddingService(model_name="all-MiniLM-L6-v2")
        vectors = await svc.embed(["document one", "document two"])
        query_vec = await svc.embed_query("search term")
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            A list of float vectors — one per input text.
            Each vector has ``len == model embedding dimension``.
        """
        if not texts:
            return []
        model = self._load_model()
        raw = await asyncio.to_thread(model.encode, texts)
        return [list(map(float, vec)) for vec in raw]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Convenience wrapper around :meth:`embed` for single inputs.
        """
        results = await self.embed([text])
        return results[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> Any:
        """Lazily load and cache the SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("embedding_model_loading", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info("embedding_model_ready", model=self._model_name)
        return self._model
