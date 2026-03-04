"""Unit tests for CopilotPipeline and related guardrail additions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    CopilotQueryRequest,
    EvidenceSource,
    PresetConfig,
    RouterIntent,
)
from app.services.copilot.pipeline import CopilotPipeline, _build_schema_summary
from app.services.copilot.sse import SSEEvent
from app.services.guardrails import GuardrailService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_preset(hops: int = 2) -> PresetConfig:
    return PresetConfig(hops=hops)


def _make_request(query: str = "Who knows Alice?") -> CopilotQueryRequest:
    return CopilotQueryRequest(query=query, session_id="sess-1")


def _synth_gen(events: list[SSEEvent]):
    """Return an async generator that yields the given SSE events."""

    async def _gen():
        for event in events:
            yield event

    return _gen()


def _make_pipeline_mocks(
    intent: RouterIntent | None = None,
    rows: list[dict] | None = None,
    synth_events: list[SSEEvent] | None = None,
    synth_events_2: list[SSEEvent] | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (mock_client, mock_router, mock_retrieval, mock_synthesiser)."""
    if intent is None:
        intent = RouterIntent(needs_graph=True, needs_docs=False)
    if rows is None:
        rows = [{"name": "Alice"}]
    if synth_events is None:
        synth_events = [
            SSEEvent(event="text_chunk", data={"text": "answer"}),
            SSEEvent(event="confidence", data={"score": 0.85, "band": "high"}),
            SSEEvent(event="done", data={}),
        ]

    mock_client = MagicMock()
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(return_value=intent)

    mock_retrieval = MagicMock()
    evidence: list[EvidenceSource] = []
    mock_retrieval.retrieve = AsyncMock(return_value=(rows, evidence))

    mock_synthesiser = MagicMock()
    if synth_events_2 is not None:
        mock_synthesiser.synthesise.side_effect = [
            _synth_gen(synth_events),
            _synth_gen(synth_events_2),
        ]
    else:
        mock_synthesiser.synthesise.return_value = _synth_gen(synth_events)

    return mock_client, mock_router, mock_retrieval, mock_synthesiser


async def _run_pipeline(
    pipeline: CopilotPipeline,
    mock_client: MagicMock,
    mock_router: MagicMock,
    mock_retrieval: MagicMock,
    mock_synthesiser: MagicMock,
    request: CopilotQueryRequest | None = None,
    preset: PresetConfig | None = None,
) -> list[SSEEvent]:
    """Patch services and collect all SSE events from the pipeline."""
    if request is None:
        request = _make_request()
    if preset is None:
        preset = _make_preset()

    events: list[SSEEvent] = []

    with (
        patch(
            "app.services.copilot.pipeline.RouterService",
            return_value=mock_router,
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService",
            return_value=mock_retrieval,
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService",
            return_value=mock_synthesiser,
        ),
    ):
        async for event in pipeline.execute(
            request=request,
            neo4j_service=None,
            openrouter_client=mock_client,
            preset_config=preset,
            session_id="sess-1",
        ):
            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Full flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow_emits_status_and_synthesis_events():
    """Pipeline emits status:routing, status:retrieving, then synthesis events."""
    pipeline = CopilotPipeline()
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks()

    events = await _run_pipeline(
        pipeline, mock_client, mock_router, mock_retrieval, mock_synthesiser
    )

    status_events = [e for e in events if e.event == "status"]
    assert any(e.data.get("stage") == "routing" for e in status_events)
    assert any(e.data.get("stage") == "retrieving" for e in status_events)

    text_events = [e for e in events if e.event == "text_chunk"]
    assert len(text_events) == 1
    assert text_events[0].data["text"] == "answer"

    done_events = [e for e in events if e.event == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_router_classify_called_with_query():
    """RouterService.classify receives the query string."""
    pipeline = CopilotPipeline()
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks()

    await _run_pipeline(
        pipeline,
        mock_client,
        mock_router,
        mock_retrieval,
        mock_synthesiser,
        request=_make_request("Find paths between Alice and Bob"),
    )

    mock_router.classify.assert_awaited_once()
    call_kwargs = mock_router.classify.call_args.kwargs
    assert call_kwargs["query"] == "Find paths between Alice and Bob"


@pytest.mark.asyncio
async def test_retrieval_called_with_intent():
    """GraphRetrievalService.retrieve receives the RouterIntent."""
    pipeline = CopilotPipeline()
    intent = RouterIntent(needs_graph=True, cypher_hint="MATCH (n) RETURN n")
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks(
        intent=intent
    )

    await _run_pipeline(
        pipeline, mock_client, mock_router, mock_retrieval, mock_synthesiser
    )

    mock_retrieval.retrieve.assert_awaited_once()
    call_kwargs = mock_retrieval.retrieve.call_args.kwargs
    assert call_kwargs["intent"] is intent


# ---------------------------------------------------------------------------
# Re-retrieval on low confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_re_retrieval_triggered_on_low_confidence():
    """When confidence < 0.40, pipeline emits status:re_retrieving and re-synthesises."""
    pipeline = CopilotPipeline()

    low_conf_synth = [
        SSEEvent(event="text_chunk", data={"text": "first answer"}),
        SSEEvent(event="confidence", data={"score": 0.25, "band": "low"}),
        SSEEvent(event="done", data={}),
    ]
    second_synth = [
        SSEEvent(event="text_chunk", data={"text": "better answer"}),
        SSEEvent(event="confidence", data={"score": 0.72, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks(
        synth_events=low_conf_synth,
        synth_events_2=second_synth,
    )

    events = await _run_pipeline(
        pipeline, mock_client, mock_router, mock_retrieval, mock_synthesiser
    )

    status_stages = [
        e.data.get("stage") for e in events if e.event == "status"
    ]
    assert "re_retrieving" in status_stages

    # Retrieval called twice: first pass + re-retrieval
    assert mock_retrieval.retrieve.await_count == 2

    # Synthesiser called twice
    assert mock_synthesiser.synthesise.call_count == 2

    # Both text chunks appear in output
    text_chunks = [e.data["text"] for e in events if e.event == "text_chunk"]
    assert "first answer" in text_chunks
    assert "better answer" in text_chunks


@pytest.mark.asyncio
async def test_no_re_retrieval_on_high_confidence():
    """When confidence >= 0.40, re-retrieval is NOT triggered."""
    pipeline = CopilotPipeline()

    synth_events = [
        SSEEvent(event="confidence", data={"score": 0.80, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks(
        synth_events=synth_events
    )

    events = await _run_pipeline(
        pipeline, mock_client, mock_router, mock_retrieval, mock_synthesiser
    )

    status_stages = [
        e.data.get("stage") for e in events if e.event == "status"
    ]
    assert "re_retrieving" not in status_stages
    assert mock_retrieval.retrieve.await_count == 1
    assert mock_synthesiser.synthesise.call_count == 1


@pytest.mark.asyncio
async def test_re_retrieval_uses_expanded_hops():
    """Re-retrieval intent includes incremented hops in the cypher_hint."""
    pipeline = CopilotPipeline()

    low_conf_synth = [
        SSEEvent(event="confidence", data={"score": 0.10, "band": "low"}),
        SSEEvent(event="done", data={}),
    ]
    second_synth = [
        SSEEvent(event="done", data={}),
    ]
    mock_client, mock_router, mock_retrieval, mock_synthesiser = _make_pipeline_mocks(
        synth_events=low_conf_synth,
        synth_events_2=second_synth,
    )

    await _run_pipeline(
        pipeline,
        mock_client,
        mock_router,
        mock_retrieval,
        mock_synthesiser,
        preset=_make_preset(hops=2),
    )

    # Second call to retrieve has re_intent with expanded hops hint
    second_call_kwargs = mock_retrieval.retrieve.call_args_list[1].kwargs
    re_intent: RouterIntent = second_call_kwargs["intent"]
    assert re_intent.cypher_hint is not None
    assert "3" in re_intent.cypher_hint  # hops=2+1=3


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_yields_error_event():
    """When the pipeline exceeds the timeout, an error event is emitted."""
    pipeline = CopilotPipeline()
    mock_client = MagicMock()
    mock_router = MagicMock()

    async def _slow_classify(**kwargs):
        await asyncio.sleep(10.0)
        return RouterIntent()

    mock_router.classify = _slow_classify
    mock_retrieval = MagicMock()
    mock_synthesiser = MagicMock()

    events: list[SSEEvent] = []
    with (
        patch("app.services.copilot.pipeline._PIPELINE_TIMEOUT_S", 0.01),
        patch(
            "app.services.copilot.pipeline.RouterService",
            return_value=mock_router,
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService",
            return_value=mock_retrieval,
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService",
            return_value=mock_synthesiser,
        ),
    ):
        async for event in pipeline.execute(
            request=_make_request(),
            neo4j_service=None,
            openrouter_client=mock_client,
            preset_config=_make_preset(),
            session_id="sess-timeout",
        ):
            events.append(event)

    error_events = [e for e in events if e.event == "error"]
    assert len(error_events) == 1
    assert "timed out" in error_events[0].data["message"].lower()


# ---------------------------------------------------------------------------
# Semaphore (guardrail)
# ---------------------------------------------------------------------------


def test_check_copilot_available_when_free():
    """Guardrail returns allowed=True when semaphore is not locked."""
    svc = GuardrailService()
    sem = asyncio.Semaphore(1)
    result = svc.check_copilot_available(sem)
    assert result.allowed is True


@pytest.mark.asyncio
async def test_check_copilot_available_when_locked():
    """Guardrail returns allowed=False when semaphore is locked."""
    svc = GuardrailService()
    sem = asyncio.Semaphore(1)
    await sem.acquire()  # lock it
    try:
        result = svc.check_copilot_available(sem)
        assert result.allowed is False
        assert result.detail is not None
        assert result.detail["hard_limit"] == 1
    finally:
        sem.release()


def test_copilot_timeout_ms_in_hard_limits():
    """COPILOT_TIMEOUT_MS is present in GuardrailService.HARD_LIMITS."""
    assert GuardrailService.HARD_LIMITS["copilot_timeout_ms"] == 120_000


def test_max_concurrent_copilot_in_hard_limits():
    """MAX_CONCURRENT_COPILOT is present in GuardrailService.HARD_LIMITS."""
    assert GuardrailService.HARD_LIMITS["max_concurrent_copilot"] == 1


# ---------------------------------------------------------------------------
# _build_schema_summary helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_schema_summary_none_service():
    """Returns empty string when neo4j_service is None."""
    result = await _build_schema_summary(None)
    assert result == ""


@pytest.mark.asyncio
async def test_build_schema_summary_with_schema():
    """Returns a formatted summary string from schema data."""
    mock_svc = MagicMock()
    mock_svc.get_schema = AsyncMock(
        return_value={
            "labels": [{"name": "Person"}, {"name": "Company"}],
            "relationship_types": [{"name": "KNOWS"}, {"name": "WORKS_AT"}],
        }
    )
    result = await _build_schema_summary(mock_svc)
    assert "Person" in result
    assert "KNOWS" in result


@pytest.mark.asyncio
async def test_build_schema_summary_handles_failure():
    """Returns empty string when get_schema raises."""
    mock_svc = MagicMock()
    mock_svc.get_schema = AsyncMock(side_effect=RuntimeError("connection lost"))
    result = await _build_schema_summary(mock_svc)
    assert result == ""
