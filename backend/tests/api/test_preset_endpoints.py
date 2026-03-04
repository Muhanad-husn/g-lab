"""API-level tests for config/preset endpoints."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dependencies import get_db, get_openrouter
from app.models.db import Base
from app.routers import config_presets as config_presets_router
from app.services.copilot.openrouter import OpenRouterClient
from app.services.preset_service import PresetService


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def preset_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client with in-memory DB, presets seeded, no OpenRouter."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )

    # Seed system presets
    svc = PresetService()
    async with factory() as db:
        await svc.seed_system_presets(db)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    def override_get_openrouter(_request: Request) -> OpenRouterClient | None:
        return None

    test_app = FastAPI()
    test_app.include_router(config_presets_router.router, prefix="/api/v1/config")
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_openrouter] = override_get_openrouter

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as c:
        yield c

    await engine.dispose()


@pytest.fixture()
async def preset_client_with_openrouter() -> (
    AsyncGenerator[tuple[AsyncClient, MagicMock], None]
):
    """Client variant with a mocked OpenRouter client."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )

    svc = PresetService()
    async with factory() as db:
        await svc.seed_system_presets(db)

    mock_or = MagicMock(spec=OpenRouterClient)
    mock_or.list_models = AsyncMock(
        return_value=[
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"},
            {"id": "openai/gpt-4o", "name": "GPT-4o"},
        ]
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    def override_get_openrouter(_request: Request) -> OpenRouterClient | None:
        return mock_or  # type: ignore[return-value]

    test_app = FastAPI()
    test_app.include_router(config_presets_router.router, prefix="/api/v1/config")
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_openrouter] = override_get_openrouter

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as c:
        yield c, mock_or

    await engine.dispose()


# ---------------------------------------------------------------------------
# List presets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_presets_returns_3_system(preset_client: AsyncClient) -> None:
    """Seeded DB should return exactly 3 system presets."""
    resp = await preset_client.get("/api/v1/config/presets")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 3
    system_ids = {p["id"] for p in data}
    assert "preset-standard" in system_ids
    assert "preset-quick" in system_ids
    assert "preset-deep" in system_ids
    for p in data:
        assert p["is_system"] is True


# ---------------------------------------------------------------------------
# Create user preset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_preset_returns_201(preset_client: AsyncClient) -> None:
    resp = await preset_client.post(
        "/api/v1/config/presets",
        json={
            "name": "My Custom Preset",
            "config": {
                "hops": 3,
                "expansionLimit": 30,
                "models": {
                    "router": "anthropic/claude-3-haiku-20240307",
                    "graphRetrieval": "anthropic/claude-3-5-sonnet-20241022",
                    "synthesiser": "anthropic/claude-sonnet-4-20250514",
                },
                "tokenBudgets": {
                    "router": 256,
                    "graphRetrieval": 512,
                    "synthesiser": 4096,
                },
            },
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "My Custom Preset"
    assert data["is_system"] is False
    assert data["config"]["hops"] == 3
    assert "id" in data


@pytest.mark.asyncio
async def test_create_preset_appears_in_list(preset_client: AsyncClient) -> None:
    await preset_client.post(
        "/api/v1/config/presets",
        json={
            "name": "Listed Preset",
            "config": {
                "hops": 2,
                "expansionLimit": 25,
                "models": {},
                "tokenBudgets": {},
            },
        },
    )
    resp = await preset_client.get("/api/v1/config/presets")
    names = [p["name"] for p in resp.json()["data"]]
    assert "Listed Preset" in names


# ---------------------------------------------------------------------------
# Update user preset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_preset_success(preset_client: AsyncClient) -> None:
    create_resp = await preset_client.post(
        "/api/v1/config/presets",
        json={
            "name": "To Update",
            "config": {"hops": 1, "expansionLimit": 10, "models": {}, "tokenBudgets": {}},
        },
    )
    preset_id = create_resp.json()["data"]["id"]

    resp = await preset_client.put(
        f"/api/v1/config/presets/{preset_id}",
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_system_preset_returns_403(preset_client: AsyncClient) -> None:
    resp = await preset_client.put(
        "/api/v1/config/presets/preset-standard",
        json={"name": "Hacked"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_nonexistent_preset_returns_404(preset_client: AsyncClient) -> None:
    resp = await preset_client.put(
        "/api/v1/config/presets/does-not-exist",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete user preset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_preset_success(preset_client: AsyncClient) -> None:
    create_resp = await preset_client.post(
        "/api/v1/config/presets",
        json={
            "name": "To Delete",
            "config": {"hops": 1, "expansionLimit": 10, "models": {}, "tokenBudgets": {}},
        },
    )
    preset_id = create_resp.json()["data"]["id"]

    resp = await preset_client.delete(f"/api/v1/config/presets/{preset_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == preset_id

    # Confirm gone from list
    list_resp = await preset_client.get("/api/v1/config/presets")
    ids = [p["id"] for p in list_resp.json()["data"]]
    assert preset_id not in ids


@pytest.mark.asyncio
async def test_delete_system_preset_returns_403(preset_client: AsyncClient) -> None:
    resp = await preset_client.delete("/api/v1/config/presets/preset-quick")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_preset_returns_404(preset_client: AsyncClient) -> None:
    resp = await preset_client.delete("/api/v1/config/presets/ghost-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Models endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_returns_503_when_no_key(preset_client: AsyncClient) -> None:
    resp = await preset_client.get("/api/v1/config/models")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_list_models_returns_model_list(
    preset_client_with_openrouter: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock_or = preset_client_with_openrouter
    resp = await client.get("/api/v1/config/models")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["id"] == "anthropic/claude-3-haiku"
    mock_or.list_models.assert_called_once()
