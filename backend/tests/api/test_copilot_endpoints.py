"""API-level tests for copilot endpoints.

Tests cover:
- POST /copilot/query: SSE stream format, 503 (no openrouter), 409 (concurrent)
- GET  /copilot/history/{session_id}: list messages, empty list
- Conversation stored after stream completes
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dependencies import (
    get_action_logger,
    get_copilot_semaphore,
    get_db,
    get_openrouter,
)
from app.models.db import Base
from app.routers import copilot as copilot_router
from app.services.action_log import ActionLogger
from app.services.conversation_service import ConversationService
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.sse import SSEEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sse_events(*events: SSEEvent) -> list[SSEEvent]:
    return list(events)


async def _async_gen(*events: SSEEvent) -> AsyncGenerator[SSEEvent, None]:
    for ev in events:
        yield ev


def _parse_sse_body(content: bytes) -> list[dict[str, Any]]:
    """Parse SSE wire format into list of {event, data} dicts."""
    result: list[dict[str, Any]] = []
    blocks = content.decode().strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_type: str | None = None
        data_str: str | None = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
        if event_type and data_str is not None:
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str  # type: ignore[assignment]
            result.append({"event": event_type, "data": data})
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def _engine() -> AsyncGenerator[Any, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def copilot_client_no_openrouter(
    _engine: Any,
) -> AsyncGenerator[AsyncClient, None]:
    """Client without OpenRouter configured (key empty)."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _engine, expire_on_commit=False
    )

    semaphore = asyncio.Semaphore(1)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    with tempfile.TemporaryDirectory(prefix="glab_copilot_test_") as tmp:
        action_logger = ActionLogger(
            data_dir=Path(tmp), session_factory=factory
        )

        def override_action_logger(_req: Request) -> ActionLogger:
            return action_logger

        def override_openrouter(_req: Request) -> OpenRouterClient | None:
            return None

        def override_semaphore(_req: Request) -> asyncio.Semaphore:
            return semaphore

        test_app = FastAPI()
        test_app.include_router(copilot_router.router, prefix="/api/v1/copilot")
        test_app.dependency_overrides[get_db] = override_get_db
        test_app.dependency_overrides[get_action_logger] = override_action_logger
        test_app.dependency_overrides[get_openrouter] = override_openrouter
        test_app.dependency_overrides[get_copilot_semaphore] = override_semaphore
        test_app.state.db_session_factory = factory

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as c:
            yield c


CopilotClientFixture = tuple[
    AsyncClient,
    MagicMock,
    asyncio.Semaphore,
    async_sessionmaker[AsyncSession],
]


@pytest.fixture()
async def copilot_client(
    _engine: Any,
) -> AsyncGenerator[CopilotClientFixture, None]:
    """Client with a mocked OpenRouter client and free semaphore.

    Yields ``(client, mock_openrouter, semaphore, factory)``.
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _engine, expire_on_commit=False
    )

    semaphore = asyncio.Semaphore(1)
    mock_or = MagicMock(spec=OpenRouterClient)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    with tempfile.TemporaryDirectory(prefix="glab_copilot_test_") as tmp:
        action_logger = ActionLogger(
            data_dir=Path(tmp), session_factory=factory
        )

        def override_action_logger(_req: Request) -> ActionLogger:
            return action_logger

        def override_openrouter(_req: Request) -> OpenRouterClient | None:
            return mock_or  # type: ignore[return-value]

        def override_semaphore(_req: Request) -> asyncio.Semaphore:
            return semaphore

        test_app = FastAPI()
        test_app.include_router(copilot_router.router, prefix="/api/v1/copilot")
        test_app.dependency_overrides[get_db] = override_get_db
        test_app.dependency_overrides[get_action_logger] = override_action_logger
        test_app.dependency_overrides[get_openrouter] = override_openrouter
        test_app.dependency_overrides[get_copilot_semaphore] = override_semaphore
        test_app.state.db_session_factory = factory

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as c:
            yield c, mock_or, semaphore, factory


# ---------------------------------------------------------------------------
# 503 — OpenRouter not configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_returns_503_without_openrouter(
    copilot_client_no_openrouter: AsyncClient,
) -> None:
    client = copilot_client_no_openrouter
    resp = await client.post(
        "/api/v1/copilot/query",
        json={"query": "Who are the key suspects?", "session_id": "sess-1"},
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 409 — Semaphore locked (concurrent request)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_returns_409_when_semaphore_locked(
    copilot_client: tuple[AsyncClient, MagicMock, asyncio.Semaphore, Any],
) -> None:
    client, _mock_or, semaphore, _factory = copilot_client

    # Lock the semaphore to simulate an in-flight request
    await semaphore.acquire()
    try:
        resp = await client.post(
            "/api/v1/copilot/query",
            json={"query": "Test concurrent", "session_id": "sess-busy"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "copilot_busy"
    finally:
        semaphore.release()


# ---------------------------------------------------------------------------
# SSE stream format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_streams_sse_events(
    copilot_client: tuple[AsyncClient, MagicMock, asyncio.Semaphore, Any],
) -> None:
    client, _mock_or, _semaphore, _factory = copilot_client

    fake_events = [
        SSEEvent(event="status", data={"status": "routing"}),
        SSEEvent(event="status", data={"status": "retrieving"}),
        SSEEvent(event="text_chunk", data={"text": "Hello "}),
        SSEEvent(event="text_chunk", data={"text": "world"}),
        SSEEvent(event="confidence", data={"score": 0.85, "label": "high"}),
        SSEEvent(event="done", data={"finish_reason": "stop"}),
    ]

    with patch(
        "app.routers.copilot._pipeline.execute",
        return_value=_async_gen(*fake_events),
    ):
        resp = await client.post(
            "/api/v1/copilot/query",
            json={"query": "Who did it?", "session_id": "sess-stream"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse_body(resp.content)
    assert len(events) == 6

    event_types = [e["event"] for e in events]
    assert event_types == [
        "status", "status", "text_chunk", "text_chunk", "confidence", "done"
    ]

    status_events = [e for e in events if e["event"] == "status"]
    assert status_events[0]["data"]["status"] == "routing"
    assert status_events[1]["data"]["status"] == "retrieving"

    text_events = [e for e in events if e["event"] == "text_chunk"]
    assert text_events[0]["data"]["text"] == "Hello "
    assert text_events[1]["data"]["text"] == "world"


@pytest.mark.asyncio
async def test_query_sse_headers(
    copilot_client: tuple[AsyncClient, MagicMock, asyncio.Semaphore, Any],
) -> None:
    client, _mock_or, _semaphore, _factory = copilot_client

    fake_events = [SSEEvent(event="done", data={"finish_reason": "stop"})]

    with patch(
        "app.routers.copilot._pipeline.execute",
        return_value=_async_gen(*fake_events),
    ):
        resp = await client.post(
            "/api/v1/copilot/query",
            json={"query": "Test headers", "session_id": "sess-hdr"},
        )

    assert resp.headers.get("cache-control") == "no-cache"
    assert resp.headers.get("x-accel-buffering") == "no"


# ---------------------------------------------------------------------------
# Conversation storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_stores_conversation_after_stream(
    copilot_client: CopilotClientFixture,
) -> None:
    client, _mock_or, _semaphore, factory = copilot_client

    fake_events = [
        SSEEvent(event="text_chunk", data={"text": "The answer is "}),
        SSEEvent(event="text_chunk", data={"text": "42."}),
        SSEEvent(event="done", data={"finish_reason": "stop"}),
    ]

    with patch(
        "app.routers.copilot._pipeline.execute",
        return_value=_async_gen(*fake_events),
    ):
        await client.post(
            "/api/v1/copilot/query",
            json={"query": "What is the answer?", "session_id": "sess-store"},
        )

    # Verify conversation was persisted
    svc = ConversationService()
    async with factory() as db:
        history = await svc.get_history(db, "sess-store")

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "What is the answer?"
    assert history[1].role == "assistant"
    assert history[1].content == "The answer is 42."


@pytest.mark.asyncio
async def test_query_does_not_store_empty_response(
    copilot_client: CopilotClientFixture,
) -> None:
    """If the stream yields no text_chunk events, nothing is stored."""
    client, _mock_or, _semaphore, factory = copilot_client

    fake_events = [SSEEvent(event="done", data={"finish_reason": "stop"})]

    with patch(
        "app.routers.copilot._pipeline.execute",
        return_value=_async_gen(*fake_events),
    ):
        await client.post(
            "/api/v1/copilot/query",
            json={"query": "Silent query", "session_id": "sess-empty"},
        )

    svc = ConversationService()
    async with factory() as db:
        history = await svc.get_history(db, "sess-empty")

    assert history == []


# ---------------------------------------------------------------------------
# GET /history/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_returns_empty_list_for_new_session(
    copilot_client: tuple[AsyncClient, MagicMock, asyncio.Semaphore, Any],
) -> None:
    client, _mock_or, _semaphore, _factory = copilot_client
    resp = await client.get("/api/v1/copilot/history/new-session-xyz")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == []


@pytest.mark.asyncio
async def test_history_returns_messages_after_query(
    copilot_client: CopilotClientFixture,
) -> None:
    client, _mock_or, _semaphore, factory = copilot_client

    # Pre-seed conversation directly via service
    svc = ConversationService()
    async with factory() as db:
        await svc.save_message(db, "sess-hist", "user", "My question")
        await svc.save_message(db, "sess-hist", "assistant", "My answer")

    resp = await client.get("/api/v1/copilot/history/sess-hist")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[0]["content"] == "My question"
    assert data[1]["role"] == "assistant"
    assert data[1]["content"] == "My answer"


@pytest.mark.asyncio
async def test_history_respects_limit_param(
    copilot_client: CopilotClientFixture,
) -> None:
    client, _mock_or, _semaphore, factory = copilot_client

    svc = ConversationService()
    async with factory() as db:
        for i in range(10):
            await svc.save_message(db, "sess-lim", "user", f"msg-{i}")

    resp = await client.get("/api/v1/copilot/history/sess-lim?limit=3")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 3


# ---------------------------------------------------------------------------
# Timeout → error event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_yields_error_event_on_timeout(
    copilot_client: tuple[AsyncClient, MagicMock, asyncio.Semaphore, Any],
) -> None:
    """If the pipeline yields a timeout error SSE event, it is forwarded."""
    client, _mock_or, _semaphore, _factory = copilot_client

    fake_events = [
        SSEEvent(
            event="error",
            data={"code": "timeout", "message": "Copilot request timed out"},
        ),
    ]

    with patch(
        "app.routers.copilot._pipeline.execute",
        return_value=_async_gen(*fake_events),
    ):
        resp = await client.post(
            "/api/v1/copilot/query",
            json={"query": "Slow query", "session_id": "sess-timeout"},
        )

    assert resp.status_code == 200  # SSE always 200 once streaming starts
    events = _parse_sse_body(resp.content)
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["code"] == "timeout"
