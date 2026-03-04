"""Unit tests for PresetService."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import Base
from app.models.schemas import PresetConfig, PresetCreate, PresetUpdate
from app.services.preset_service import PresetService


@pytest.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def svc() -> PresetService:
    return PresetService()


# ---------------------------------------------------------------------------
# Seed system presets
# ---------------------------------------------------------------------------


async def test_seed_creates_three_system_presets(
    db: AsyncSession, svc: PresetService
) -> None:
    await svc.seed_system_presets(db)
    presets = await svc.list_all(db)
    system = [p for p in presets if p.is_system]
    assert len(system) == 3
    names = {p.name for p in system}
    assert "Standard Investigation" in names
    assert "Quick Scan" in names
    assert "Deep Dive" in names


async def test_seed_is_idempotent(
    db: AsyncSession, svc: PresetService
) -> None:
    await svc.seed_system_presets(db)
    await svc.seed_system_presets(db)
    presets = await svc.list_all(db)
    system = [p for p in presets if p.is_system]
    assert len(system) == 3


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def test_create_user_preset(
    db: AsyncSession, svc: PresetService
) -> None:
    resp = await svc.create(
        db,
        PresetCreate(name="My Preset", config=PresetConfig(hops=3)),
    )
    assert resp.name == "My Preset"
    assert resp.is_system is False
    assert resp.config.hops == 3
    assert resp.id.startswith("preset-")


async def test_get_preset(
    db: AsyncSession, svc: PresetService
) -> None:
    created = await svc.create(
        db,
        PresetCreate(name="Test", config=PresetConfig()),
    )
    fetched = await svc.get(db, created.id)
    assert fetched is not None
    assert fetched.id == created.id


async def test_get_nonexistent_returns_none(
    db: AsyncSession, svc: PresetService
) -> None:
    assert await svc.get(db, "nope") is None


async def test_update_user_preset(
    db: AsyncSession, svc: PresetService
) -> None:
    created = await svc.create(
        db,
        PresetCreate(name="Old", config=PresetConfig()),
    )
    updated = await svc.update(
        db,
        created.id,
        PresetUpdate(name="New", config=PresetConfig(hops=4)),
    )
    assert updated is not None
    assert updated.name == "New"
    assert updated.config.hops == 4


async def test_update_nonexistent_returns_none(
    db: AsyncSession, svc: PresetService
) -> None:
    assert await svc.update(db, "nope", PresetUpdate(name="x")) is None


async def test_delete_user_preset(
    db: AsyncSession, svc: PresetService
) -> None:
    created = await svc.create(
        db,
        PresetCreate(name="Temp", config=PresetConfig()),
    )
    assert await svc.delete(db, created.id) is True
    assert await svc.get(db, created.id) is None


async def test_delete_nonexistent_returns_false(
    db: AsyncSession, svc: PresetService
) -> None:
    assert await svc.delete(db, "nope") is False


# ---------------------------------------------------------------------------
# System preset immutability
# ---------------------------------------------------------------------------


async def test_update_system_preset_raises(
    db: AsyncSession, svc: PresetService
) -> None:
    await svc.seed_system_presets(db)
    with pytest.raises(PermissionError, match="Cannot modify"):
        await svc.update(
            db,
            "preset-standard",
            PresetUpdate(name="Hacked"),
        )


async def test_delete_system_preset_raises(
    db: AsyncSession, svc: PresetService
) -> None:
    await svc.seed_system_presets(db)
    with pytest.raises(PermissionError, match="Cannot delete"):
        await svc.delete(db, "preset-standard")


# ---------------------------------------------------------------------------
# Listing order
# ---------------------------------------------------------------------------


async def test_list_system_before_user(
    db: AsyncSession, svc: PresetService
) -> None:
    await svc.seed_system_presets(db)
    await svc.create(
        db,
        PresetCreate(name="Zzz User", config=PresetConfig()),
    )
    presets = await svc.list_all(db)
    # System presets come first
    system_indices = [i for i, p in enumerate(presets) if p.is_system]
    user_indices = [i for i, p in enumerate(presets) if not p.is_system]
    if system_indices and user_indices:
        assert max(system_indices) < min(user_indices)
