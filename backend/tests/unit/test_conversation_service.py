"""Unit tests for ConversationService."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import Base
from app.services.conversation_service import ConversationService

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# save_message + get_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_retrieve_single_message(db_session: AsyncSession) -> None:
    svc = ConversationService()
    msg = await svc.save_message(db_session, "sess-1", "user", "Hello?")
    assert msg.id is not None
    assert msg.session_id == "sess-1"
    assert msg.role == "user"
    assert msg.content == "Hello?"
    assert msg.timestamp is not None

    history = await svc.get_history(db_session, "sess-1")
    assert len(history) == 1
    assert history[0].id == msg.id


@pytest.mark.asyncio
async def test_save_user_and_assistant_messages(db_session: AsyncSession) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-2", "user", "Query")
    await svc.save_message(db_session, "sess-2", "assistant", "Answer")

    history = await svc.get_history(db_session, "sess-2")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


@pytest.mark.asyncio
async def test_get_history_empty_for_unknown_session(db_session: AsyncSession) -> None:
    svc = ConversationService()
    history = await svc.get_history(db_session, "no-such-session")
    assert history == []


@pytest.mark.asyncio
async def test_get_history_isolates_by_session(db_session: AsyncSession) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-A", "user", "A message")
    await svc.save_message(db_session, "sess-B", "user", "B message")

    hist_a = await svc.get_history(db_session, "sess-A")
    hist_b = await svc.get_history(db_session, "sess-B")

    assert len(hist_a) == 1
    assert hist_a[0].content == "A message"
    assert len(hist_b) == 1
    assert hist_b[0].content == "B message"


@pytest.mark.asyncio
async def test_get_history_ordering_oldest_first(db_session: AsyncSession) -> None:
    svc = ConversationService()
    contents = ["first", "second", "third"]
    for c in contents:
        await svc.save_message(db_session, "sess-ord", "user", c)

    history = await svc.get_history(db_session, "sess-ord")
    assert [m.content for m in history] == contents


@pytest.mark.asyncio
async def test_get_history_respects_limit(db_session: AsyncSession) -> None:
    svc = ConversationService()
    for i in range(10):
        await svc.save_message(db_session, "sess-lim", "user", f"msg-{i}")

    history = await svc.get_history(db_session, "sess-lim", limit=4)
    assert len(history) == 4
    # Oldest first — should be first 4
    assert history[0].content == "msg-0"


# ---------------------------------------------------------------------------
# save_message metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_message_with_metadata(db_session: AsyncSession) -> None:
    svc = ConversationService()
    meta = {"confidence": 0.9, "model": "claude-3"}
    msg = await svc.save_message(
        db_session, "sess-meta", "assistant", "Ans", metadata=meta
    )
    assert msg.metadata == meta


@pytest.mark.asyncio
async def test_save_message_without_metadata(db_session: AsyncSession) -> None:
    svc = ConversationService()
    msg = await svc.save_message(db_session, "sess-nometa", "user", "Q")
    assert msg.metadata is None


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_history_removes_all_for_session(db_session: AsyncSession) -> None:
    svc = ConversationService()
    for i in range(3):
        await svc.save_message(db_session, "sess-clr", "user", f"msg-{i}")

    deleted = await svc.clear_history(db_session, "sess-clr")
    assert deleted == 3

    history = await svc.get_history(db_session, "sess-clr")
    assert history == []


@pytest.mark.asyncio
async def test_clear_history_does_not_affect_other_sessions(
    db_session: AsyncSession,
) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-keep", "user", "keep me")
    await svc.save_message(db_session, "sess-del", "user", "delete me")

    await svc.clear_history(db_session, "sess-del")

    kept = await svc.get_history(db_session, "sess-keep")
    assert len(kept) == 1


@pytest.mark.asyncio
async def test_clear_history_returns_zero_for_unknown_session(
    db_session: AsyncSession,
) -> None:
    svc = ConversationService()
    deleted = await svc.clear_history(db_session, "no-such")
    assert deleted == 0
