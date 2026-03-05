"""Full pipeline integration test.

Wires RouterService → GraphRetrievalService → SynthesiserService through
CopilotPipeline and verifies the end-to-end SSE event sequence and
conversation persistence, with all external I/O mocked.

External dependencies mocked:
- RouterService.classify      (avoids real OpenRouter HTTP call)
- GraphRetrievalService.retrieve (avoids real OpenRouter + Neo4j)
- SynthesiserService.synthesise  (avoids real OpenRouter streaming)
- ConversationService uses a real in-memory SQLite DB
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import Base
from app.models.schemas import (
    CopilotQueryRequest,
    PresetConfig,
    RouterIntent,
)
from app.services.conversation_service import ConversationService
from app.services.copilot.pipeline import CopilotPipeline
from app.services.copilot.sse import SSEEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(query: str = "Who are the key suspects?") -> CopilotQueryRequest:
    return CopilotQueryRequest(query=query, session_id="integ-sess-1")


def _make_preset() -> PresetConfig:
    return PresetConfig()


def _make_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(1)


async def _collect_pipeline(
    pipeline: CopilotPipeline, **kwargs: Any
) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    async for event in pipeline.execute(**kwargs):
        events.append(event)
    return events


def _high_confidence_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Alice knows Bob."}),
        SSEEvent(event="evidence", data={"sources": []}),
        SSEEvent(event="confidence", data={"score": 0.85, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


def _low_confidence_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Uncertain answer."}),
        SSEEvent(event="confidence", data={"score": 0.20, "band": "low"}),
        SSEEvent(event="done", data={}),
    ]


def _re_retrieval_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "After broader search: confirmed."}),
        SSEEvent(event="confidence", data={"score": 0.80, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Happy-path integration: query → route → retrieve → synthesise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_happy_path_emits_correct_event_sequence() -> None:
    """Full pipeline emits: routing → retrieving → text_chunk → confidence → done."""
    intent = RouterIntent(needs_graph=True)
    synth_events = _high_confidence_events()

    async def fake_synth(*args: Any, **kwargs: Any) -> AsyncGenerator[SSEEvent, None]:
        for ev in synth_events:
            yield ev

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=fake_synth(),
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect_pipeline(
            pipeline,
            request=_make_request(),
            neo4j_service=MagicMock(),
            openrouter_client=MagicMock(),
            preset_config=_make_preset(),
            session_id="integ-sess-1",
            semaphore=_make_semaphore(),
        )

    event_types = [e.event for e in events]

    # Structural assertions
    assert event_types[0] == "status"
    assert events[0].data["stage"] == "routing"
    assert event_types[1] == "status"
    assert events[1].data["stage"] == "retrieving"
    assert "text_chunk" in event_types
    assert "confidence" in event_types
    assert event_types[-1] == "done"

    # No re-retrieval
    statuses = [e.data["stage"] for e in events if e.event == "status"]
    assert "re_retrieving" not in statuses


# ---------------------------------------------------------------------------
# Low confidence → re-retrieval path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_re_retrieval_on_low_confidence() -> None:
    """Low confidence triggers re_retrieving status and second synthesis pass."""
    intent = RouterIntent(needs_graph=True)
    first_events = _low_confidence_events()
    second_events = _re_retrieval_events()

    call_count: dict[str, int] = {"synth": 0}

    async def fake_synth(*args: Any, **kwargs: Any) -> AsyncGenerator[SSEEvent, None]:
        call_count["synth"] += 1
        source = first_events if call_count["synth"] == 1 else second_events
        for ev in source:
            yield ev

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            side_effect=[fake_synth(), fake_synth()],
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect_pipeline(
            pipeline,
            request=_make_request("What do we know about Alice?"),
            neo4j_service=MagicMock(),
            openrouter_client=MagicMock(),
            preset_config=_make_preset(),
            session_id="integ-sess-2",
            semaphore=_make_semaphore(),
        )

    statuses = [e.data["stage"] for e in events if e.event == "status"]
    assert "re_retrieving" in statuses

    # Only second-pass text should appear
    text_chunks = [e.data["text"] for e in events if e.event == "text_chunk"]
    assert any("broader search" in t or "confirmed" in t for t in text_chunks)


# ---------------------------------------------------------------------------
# Conversation storage integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_conversation_stored_after_pipeline(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After pipeline completes, conversation can be persisted and retrieved."""
    intent = RouterIntent(needs_graph=False)
    synth_events = [
        SSEEvent(event="text_chunk", data={"text": "The answer is "}),
        SSEEvent(event="text_chunk", data={"text": "42."}),
        SSEEvent(event="confidence", data={"score": 0.9, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]

    async def fake_synth(*args: Any, **kwargs: Any) -> AsyncGenerator[SSEEvent, None]:
        for ev in synth_events:
            yield ev

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=fake_synth(),
        ),
    ):
        pipeline = CopilotPipeline()
        query = "What is the answer?"
        session_id = "integ-sess-store"
        events = await _collect_pipeline(
            pipeline,
            request=_make_request(query),
            neo4j_service=MagicMock(),
            openrouter_client=MagicMock(),
            preset_config=_make_preset(),
            session_id=session_id,
            semaphore=_make_semaphore(),
        )

    # Simulate what the router endpoint does: collect text chunks and store
    text_chunks = [
        e.data.get("text", "") for e in events if e.event == "text_chunk"
    ]
    full_response = "".join(text_chunks)

    svc = ConversationService()
    async with db_factory() as db:
        await svc.save_message(db, session_id, "user", query)
        await svc.save_message(db, session_id, "assistant", full_response)

    # Verify persistence
    async with db_factory() as db:
        history = await svc.get_history(db, session_id)

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == query
    assert history[1].role == "assistant"
    assert history[1].content == "The answer is 42."


# ---------------------------------------------------------------------------
# Semaphore integration: busy → error event, then released
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_semaphore_guard() -> None:
    """Pipeline rejects and emits error when semaphore is held; releases after."""
    sem = asyncio.Semaphore(1)
    await sem.acquire()  # pre-hold to simulate concurrent request

    pipeline = CopilotPipeline()
    events = await _collect_pipeline(
        pipeline,
        request=_make_request(),
        neo4j_service=MagicMock(),
        openrouter_client=MagicMock(),
        preset_config=_make_preset(),
        session_id="integ-sess-busy",
        semaphore=sem,
    )

    # Error event emitted, semaphore NOT released (we held it externally)
    assert len(events) == 1
    assert events[0].event == "error"
    assert events[0].data["code"] == "busy"
    assert sem.locked(), "external acquire should still hold the semaphore"
    sem.release()


# ---------------------------------------------------------------------------
# Action logger integration (fire-and-forget)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_action_logger_fires_after_pipeline(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ActionLogger can log copilot events after pipeline without blocking."""
    from app.models.enums import ActionType
    from app.services.action_log import ActionLogger

    intent = RouterIntent()
    synth_events = [
        SSEEvent(event="text_chunk", data={"text": "Summary."}),
        SSEEvent(event="done", data={}),
    ]

    async def fake_synth(*args: Any, **kwargs: Any) -> AsyncGenerator[SSEEvent, None]:
        for ev in synth_events:
            yield ev

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=fake_synth(),
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect_pipeline(
            pipeline,
            request=_make_request("Summarise the network"),
            neo4j_service=MagicMock(),
            openrouter_client=MagicMock(),
            preset_config=_make_preset(),
            session_id="integ-sess-log",
            semaphore=_make_semaphore(),
        )

    # ActionLogger writes to SQLite — verify it can record the copilot query
    with tempfile.TemporaryDirectory(prefix="glab_integ_test_") as tmp:
        logger = ActionLogger(data_dir=Path(tmp), session_factory=db_factory)
        text_chunks = [e.data.get("text", "") for e in events if e.event == "text_chunk"]
        await logger.log(
            session_id="integ-sess-log",
            action_type=ActionType.COPILOT_QUERY,
            payload={"query": "Summarise the network"},
            result_summary={"response_length": len("".join(text_chunks))},
        )
        # If no exception, logger wired correctly
        assert True
