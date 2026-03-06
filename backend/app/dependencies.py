"""FastAPI dependency injection providers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.action_log import ActionLogger
from app.services.copilot.openrouter import OpenRouterClient
from app.services.documents.chromadb_client import ChromaDBClient
from app.services.documents.embeddings import EmbeddingService
from app.services.neo4j_service import Neo4jService

# Set during lifespan startup in main.py.
_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_session_factory(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Store the session factory (called once during lifespan startup)."""
    global _session_factory
    _session_factory = factory


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, closing it after use."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — lifespan not started")
    async with _session_factory() as session:
        yield session


def get_action_logger(request: Request) -> ActionLogger:
    """Return the ActionLogger from app state."""
    logger: ActionLogger | None = getattr(request.app.state, "action_logger", None)
    if logger is None:
        raise RuntimeError("ActionLogger not initialised — lifespan not started")
    return logger


def get_openrouter(request: Request) -> OpenRouterClient | None:
    """Return the OpenRouterClient from app state, or None if not configured."""
    return getattr(request.app.state, "openrouter_client", None)


def get_copilot_semaphore(request: Request) -> asyncio.Semaphore:
    """Return the copilot concurrency semaphore from app state."""
    semaphore: asyncio.Semaphore | None = getattr(
        request.app.state, "copilot_semaphore", None
    )
    if semaphore is None:
        raise RuntimeError("Copilot semaphore not initialised — lifespan not started")
    return semaphore


def get_chromadb(request: Request) -> ChromaDBClient | None:
    """Return the ChromaDBClient from app state, or None if not configured."""
    return getattr(request.app.state, "chromadb_client", None)


def get_embedding_service(request: Request) -> EmbeddingService | None:
    """Return the EmbeddingService from app state, or None if not configured."""
    return getattr(request.app.state, "embedding_service", None)


def get_reranker(request: Request) -> Any:
    """Return the RerankerService from app state, or None if not configured."""
    return getattr(request.app.state, "reranker_service", None)


def get_neo4j(request: Request) -> Neo4jService:
    """Return the Neo4j service from app state.

    Raises 503 if Neo4j is not connected (degraded mode).
    """
    neo4j_service: Neo4jService | None = getattr(
        request.app.state, "neo4j_service", None
    )
    if neo4j_service is None or not neo4j_service.is_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not available (degraded mode)",
        )
    return neo4j_service
