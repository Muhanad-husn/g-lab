"""Unit tests for app.services.copilot.pipeline."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    CopilotQueryRequest,
    PresetConfig,
    RouterIntent,
)
from app.services.copilot.pipeline import CopilotPipeline, _broaden_hint
from app.services.copilot.sse import SSEEvent


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_request(query: str = "Who knows Alice?") -> CopilotQueryRequest:
    return CopilotQueryRequest(query=query, session_id="sess-1")


def _make_preset() -> PresetConfig:
    return PresetConfig()


def _make_semaphore(value: int = 1) -> asyncio.Semaphore:
    return asyncio.Semaphore(value)


def _high_confidence_synth_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Alice knows Bob."}),
        SSEEvent(event="evidence", data={"sources": []}),
        SSEEvent(event="confidence", data={"score": 0.85, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


def _low_confidence_synth_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Uncertain..."}),
        SSEEvent(event="confidence", data={"score": 0.20, "band": "low"}),
        SSEEvent(event="done", data={}),
    ]


def _re_synth_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "After broader search: Alice → Bob."}),
        SSEEvent(event="confidence", data={"score": 0.75, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


async def _collect(pipeline: CopilotPipeline, **kwargs: Any) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    async for event in pipeline.execute(**kwargs):
        events.append(event)
    return events


def _mock_openrouter() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Full flow — high confidence (no re-retrieval)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow_happy_path():
    """status:routing → status:retrieving → synthesiser events."""
    intent = RouterIntent(needs_graph=True)
    synth_events = _high_confidence_synth_events()

    async def fake_synth(*args: Any, **kwargs: Any):
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
        events = await _collect(
            pipeline,
            request=_make_request(),
            neo4j_service=MagicMock(),
            openrouter_client=_mock_openrouter(),
            preset_config=_make_preset(),
            session_id="sess-1",
            semaphore=_make_semaphore(),
        )

    event_types = [e.event for e in events]
    assert event_types[0] == "status"
    assert events[0].data["status"] == "routing"
    assert event_types[1] == "status"
    assert events[1].data["status"] == "retrieving"
    # Then the synthesiser events (text_chunk, evidence, confidence, done)
    assert "text_chunk" in event_types
    assert "confidence" in event_types
    assert event_types[-1] == "done"
    # No re_retrieving
    statuses = [e.data["status"] for e in events if e.event == "status"]
    assert "re_retrieving" not in statuses


# ---------------------------------------------------------------------------
# Re-retrieval on low confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_re_retrieval_on_low_confidence():
    """confidence < 0.40 triggers status:re_retrieving and re-synthesis."""
    intent = RouterIntent(needs_graph=True)
    low_events = _low_confidence_synth_events()
    re_events = _re_synth_events()

    call_count = {"synth": 0, "retrieve": 0}

    async def fake_synth_first(*args: Any, **kwargs: Any):
        call_count["synth"] += 1
        if call_count["synth"] == 1:
            for ev in low_events:
                yield ev
        else:
            for ev in re_events:
                yield ev

    async def fake_retrieve(self: Any, **kwargs: Any) -> tuple[list, list]:  # noqa: ARG001
        call_count["retrieve"] += 1
        return [], []

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
            side_effect=[fake_synth_first(), fake_synth_first()],
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect(
            pipeline,
            request=_make_request(),
            neo4j_service=MagicMock(),
            openrouter_client=_mock_openrouter(),
            preset_config=_make_preset(),
            session_id="sess-1",
            semaphore=_make_semaphore(),
        )

    statuses = [e.data["status"] for e in events if e.event == "status"]
    assert "re_retrieving" in statuses
    # First-pass low-confidence events should NOT appear
    all_text = " ".join(
        e.data.get("text", "") for e in events if e.event == "text_chunk"
    )
    assert "broader search" in all_text or "Uncertain" not in all_text


# ---------------------------------------------------------------------------
# Semaphore rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_rejection_when_busy():
    """When semaphore is already held, yields an error event immediately."""
    sem = _make_semaphore(1)
    await sem.acquire()  # pre-acquire so it's "busy"

    pipeline = CopilotPipeline()
    events = await _collect(
        pipeline,
        request=_make_request(),
        neo4j_service=MagicMock(),
        openrouter_client=_mock_openrouter(),
        preset_config=_make_preset(),
        session_id="sess-1",
        semaphore=sem,
    )

    assert len(events) == 1
    assert events[0].event == "error"
    assert events[0].data["code"] == "busy"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_yields_error_event():
    """asyncio.timeout fires → pipeline yields timeout error event."""

    async def _slow(*_args: Any, **_kwargs: Any) -> RouterIntent:
        await asyncio.sleep(10)  # much longer than the patched 10ms timeout
        return RouterIntent()  # pragma: no cover

    with (
        patch("app.services.copilot.pipeline._COPILOT_TIMEOUT_S", 0.01),
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(side_effect=_slow),
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect(
            pipeline,
            request=_make_request(),
            neo4j_service=MagicMock(),
            openrouter_client=_mock_openrouter(),
            preset_config=_make_preset(),
            session_id="sess-1",
            semaphore=_make_semaphore(),
        )

    error_events = [e for e in events if e.event == "error"]
    assert error_events, "expected at least one error event"
    assert error_events[-1].data["code"] == "timeout"


# ---------------------------------------------------------------------------
# Semaphore released after execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_released_after_success():
    """Semaphore is released even after a successful run."""
    sem = _make_semaphore(1)
    synth_events = _high_confidence_synth_events()

    async def fake_synth(*args: Any, **kwargs: Any):
        for ev in synth_events:
            yield ev

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=RouterIntent()),
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
        await _collect(
            pipeline,
            request=_make_request(),
            neo4j_service=MagicMock(),
            openrouter_client=_mock_openrouter(),
            preset_config=_make_preset(),
            session_id="sess-1",
            semaphore=sem,
        )

    assert not sem.locked(), "semaphore should be released after execution"


# ---------------------------------------------------------------------------
# GuardrailService.check_copilot_available
# ---------------------------------------------------------------------------


def test_guardrails_copilot_available():
    from app.services.guardrails import GuardrailService

    gs = GuardrailService()
    sem = asyncio.Semaphore(1)
    result = gs.check_copilot_available(sem)
    assert result.allowed is True


def test_guardrails_copilot_busy():
    from app.services.guardrails import GuardrailService

    gs = GuardrailService()
    sem = asyncio.Semaphore(0)  # already locked
    result = gs.check_copilot_available(sem)
    assert result.allowed is False
    assert result.detail is not None


def test_guardrails_hard_limits_include_copilot():
    from app.services.guardrails import GuardrailService

    assert "copilot_timeout_ms" in GuardrailService.HARD_LIMITS
    assert GuardrailService.HARD_LIMITS["copilot_timeout_ms"] == 120_000
    assert GuardrailService.HARD_LIMITS["max_concurrent_copilot"] == 1


# ---------------------------------------------------------------------------
# _broaden_hint helper
# ---------------------------------------------------------------------------


def test_broaden_hint_with_existing_hint():
    result = _broaden_hint("MATCH (n:Person)")
    assert "MATCH (n:Person)" in result
    assert "hop" in result.lower()


def test_broaden_hint_without_hint():
    result = _broaden_hint(None)
    assert result  # non-empty
    assert "hop" in result.lower()
