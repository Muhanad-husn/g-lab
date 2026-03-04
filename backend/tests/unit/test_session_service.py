"""Unit tests for SessionService using in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import Base
from app.models.schemas import SessionCreate, SessionUpdate
from app.services.session_service import SessionService


@pytest.fixture()
async def db() -> AsyncSession:  # type: ignore[return]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def svc() -> SessionService:
    return SessionService()


@pytest.mark.asyncio
async def test_create_returns_session(db: AsyncSession, svc: SessionService) -> None:
    result = await svc.create(db, SessionCreate(name="Investigation Alpha"))
    assert result.name == "Investigation Alpha"
    assert result.status == "active"
    assert result.canvas_state.nodes == []
    assert result.config == {}


@pytest.mark.asyncio
async def test_get_existing(db: AsyncSession, svc: SessionService) -> None:
    created = await svc.create(db, SessionCreate(name="Get Test"))
    fetched = await svc.get(db, created.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(
    db: AsyncSession, svc: SessionService
) -> None:
    result = await svc.get(db, "no-such-id")
    assert result is None


@pytest.mark.asyncio
async def test_get_last_active_empty(db: AsyncSession, svc: SessionService) -> None:
    result = await svc.get_last_active(db)
    assert result is None


@pytest.mark.asyncio
async def test_get_last_active_returns_most_recent(
    db: AsyncSession, svc: SessionService
) -> None:
    first = await svc.create(db, SessionCreate(name="First"))
    second = await svc.create(db, SessionCreate(name="Second"))
    # Touch second to guarantee a newer updated_at (rapid creates share timestamps)
    await svc.update(db, first.id, SessionUpdate(name="First (touched)"))
    second = await svc.update(db, second.id, SessionUpdate(name="Second (touched)"))
    assert second is not None
    result = await svc.get_last_active(db)
    assert result is not None
    assert result.id == second.id


@pytest.mark.asyncio
async def test_update_name(db: AsyncSession, svc: SessionService) -> None:
    created = await svc.create(db, SessionCreate(name="Old"))
    updated = await svc.update(db, created.id, SessionUpdate(name="New"))
    assert updated is not None
    assert updated.name == "New"


@pytest.mark.asyncio
async def test_update_nonexistent_returns_none(
    db: AsyncSession, svc: SessionService
) -> None:
    result = await svc.update(db, "missing", SessionUpdate(name="X"))
    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_session(db: AsyncSession, svc: SessionService) -> None:
    created = await svc.create(db, SessionCreate(name="To Delete"))
    deleted = await svc.delete(db, created.id)
    assert deleted is True
    assert await svc.get(db, created.id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(
    db: AsyncSession, svc: SessionService
) -> None:
    result = await svc.delete(db, "ghost")
    assert result is False


@pytest.mark.asyncio
async def test_reset_clears_canvas(db: AsyncSession, svc: SessionService) -> None:
    from app.models.schemas import CanvasState, GraphNode

    created = await svc.create(db, SessionCreate(name="Reset Test"))
    canvas = CanvasState(
        nodes=[GraphNode(id="n1", labels=["Person"], properties={"name": "Alice"})]
    )
    await svc.update(db, created.id, SessionUpdate(canvas_state=canvas))

    reset = await svc.reset(db, created.id)
    assert reset is not None
    assert reset.canvas_state.nodes == []


@pytest.mark.asyncio
async def test_reset_nonexistent_returns_none(
    db: AsyncSession, svc: SessionService
) -> None:
    result = await svc.reset(db, "ghost")
    assert result is None


@pytest.mark.asyncio
async def test_list_all_returns_all_sessions(
    db: AsyncSession, svc: SessionService
) -> None:
    await svc.create(db, SessionCreate(name="A"))
    await svc.create(db, SessionCreate(name="B"))
    await svc.create(db, SessionCreate(name="C"))
    results = await svc.list_all(db)
    assert len(results) == 3
    names = {r.name for r in results}
    assert names == {"A", "B", "C"}
