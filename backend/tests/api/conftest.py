"""Shared fixtures for API tests.

Uses a minimal FastAPI app (no lifespan) with in-memory SQLite and
dependency overrides for get_db and get_action_logger.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dependencies import get_action_logger, get_db
from app.models.db import Base
from app.routers import findings as findings_router
from app.routers import sessions as sessions_router
from app.services.action_log import ActionLogger


@pytest.fixture()
async def _engine() -> AsyncGenerator[Any, None]:
    """In-memory SQLite engine with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def client(_engine: Any) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to a minimal test app with in-memory DB."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _engine, expire_on_commit=False
    )

    with tempfile.TemporaryDirectory(prefix="glab_api_test_") as tmp:
        data_dir = Path(tmp)
        action_logger = ActionLogger(data_dir=data_dir, session_factory=factory)

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            async with factory() as session:
                yield session

        def override_get_action_logger(_request: Request) -> ActionLogger:
            return action_logger

        # Build a minimal test app that includes only the routers under test
        test_app = FastAPI()
        test_app.include_router(sessions_router.router, prefix="/api/v1/sessions")
        test_app.include_router(findings_router.router, prefix="/api/v1/sessions")
        test_app.dependency_overrides[get_db] = override_get_db
        test_app.dependency_overrides[get_action_logger] = override_get_action_logger

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as c:
            yield c
