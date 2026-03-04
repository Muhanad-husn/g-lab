"""FastAPI dependency injection providers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings

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
