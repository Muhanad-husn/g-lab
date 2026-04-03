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
    msg = await svc.save_message(db_session, "sess-1", "user", "Hello?", "conv-1")
    assert msg.id is not None
    assert msg.session_id == "sess-1"
    assert msg.conversation_id == "conv-1"
    assert msg.role == "user"
    assert msg.content == "Hello?"
    assert msg.timestamp is not None

    history = await svc.get_history(db_session, "sess-1", conversation_id="conv-1")
    assert len(history) == 1
    assert history[0].id == msg.id


@pytest.mark.asyncio
async def test_save_user_and_assistant_messages(db_session: AsyncSession) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-2", "user", "Query", "conv-2")
    await svc.save_message(db_session, "sess-2", "assistant", "Answer", "conv-2")

    history = await svc.get_history(db_session, "sess-2", conversation_id="conv-2")
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
    await svc.save_message(db_session, "sess-A", "user", "A message", "conv-A")
    await svc.save_message(db_session, "sess-B", "user", "B message", "conv-B")

    hist_a = await svc.get_history(db_session, "sess-A", conversation_id="conv-A")
    hist_b = await svc.get_history(db_session, "sess-B", conversation_id="conv-B")

    assert len(hist_a) == 1
    assert hist_a[0].content == "A message"
    assert len(hist_b) == 1
    assert hist_b[0].content == "B message"


@pytest.mark.asyncio
async def test_get_history_ordering_oldest_first(db_session: AsyncSession) -> None:
    svc = ConversationService()
    contents = ["first", "second", "third"]
    for c in contents:
        await svc.save_message(db_session, "sess-ord", "user", c, "conv-ord")

    history = await svc.get_history(db_session, "sess-ord", conversation_id="conv-ord")
    assert [m.content for m in history] == contents


@pytest.mark.asyncio
async def test_get_history_respects_limit(db_session: AsyncSession) -> None:
    svc = ConversationService()
    for i in range(10):
        await svc.save_message(db_session, "sess-lim", "user", f"msg-{i}", "conv-lim")

    history = await svc.get_history(
        db_session, "sess-lim", conversation_id="conv-lim", limit=4
    )
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
        db_session, "sess-meta", "assistant", "Ans", "conv-meta", metadata=meta
    )
    assert msg.metadata == meta


@pytest.mark.asyncio
async def test_save_message_without_metadata(db_session: AsyncSession) -> None:
    svc = ConversationService()
    msg = await svc.save_message(db_session, "sess-nometa", "user", "Q", "conv-nometa")
    assert msg.metadata is None


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_history_removes_all_for_session(db_session: AsyncSession) -> None:
    svc = ConversationService()
    for i in range(3):
        await svc.save_message(db_session, "sess-clr", "user", f"msg-{i}", "conv-clr")

    deleted = await svc.clear_history(db_session, "sess-clr")
    assert deleted == 3

    history = await svc.get_history(db_session, "sess-clr", conversation_id="conv-clr")
    assert history == []


@pytest.mark.asyncio
async def test_clear_history_does_not_affect_other_sessions(
    db_session: AsyncSession,
) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-keep", "user", "keep me", "conv-keep")
    await svc.save_message(db_session, "sess-del", "user", "delete me", "conv-del")

    await svc.clear_history(db_session, "sess-del")

    kept = await svc.get_history(db_session, "sess-keep", conversation_id="conv-keep")
    assert len(kept) == 1


@pytest.mark.asyncio
async def test_clear_history_returns_zero_for_unknown_session(
    db_session: AsyncSession,
) -> None:
    svc = ConversationService()
    deleted = await svc.clear_history(db_session, "no-such")
    assert deleted == 0


# ---------------------------------------------------------------------------
# Multi-conversation support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_history_without_conv_id_returns_latest(
    db_session: AsyncSession,
) -> None:
    """When no conversation_id is given, get_history returns the latest conversation."""
    svc = ConversationService()
    await svc.save_message(db_session, "sess-mc", "user", "old msg", "conv-old")
    await svc.save_message(db_session, "sess-mc", "user", "new msg", "conv-new")

    # No conversation_id — should return the latest (conv-new)
    history = await svc.get_history(db_session, "sess-mc")
    assert len(history) == 1
    assert history[0].content == "new msg"


@pytest.mark.asyncio
async def test_list_conversations(db_session: AsyncSession) -> None:
    svc = ConversationService()
    await svc.save_message(db_session, "sess-lc", "user", "First conv Q1", "conv-1")
    await svc.save_message(db_session, "sess-lc", "assistant", "First conv A1", "conv-1")
    await svc.save_message(db_session, "sess-lc", "user", "Second conv Q1", "conv-2")

    convs = await svc.list_conversations(db_session, "sess-lc")
    assert len(convs) == 2
    # Newest first
    assert convs[0].id == "conv-2"
    assert convs[1].id == "conv-1"
    assert convs[0].message_count == 1
    assert convs[1].message_count == 2
    assert "First conv Q1" in convs[1].preview
    assert "Second conv Q1" in convs[0].preview


@pytest.mark.asyncio
async def test_get_active_conversation_id(db_session: AsyncSession) -> None:
    svc = ConversationService()
    # No messages → None
    active = await svc.get_active_conversation_id(db_session, "sess-empty")
    assert active is None

    await svc.save_message(db_session, "sess-act", "user", "msg1", "conv-old")
    await svc.save_message(db_session, "sess-act", "user", "msg2", "conv-new")

    active = await svc.get_active_conversation_id(db_session, "sess-act")
    assert active == "conv-new"


@pytest.mark.asyncio
async def test_start_new_conversation_returns_uuid(db_session: AsyncSession) -> None:
    svc = ConversationService()
    conv_id = await svc.start_new_conversation("sess-1")
    assert conv_id is not None
    assert len(conv_id) == 36  # UUID format
