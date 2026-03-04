"""Unit tests for app.services.copilot.synthesiser."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.copilot.sse import SSEEvent
from app.services.copilot.synthesiser import SynthesiserService, _format_graph_results

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fake_stream(*chunks: str):
    """Async generator that yields the given string chunks."""
    for chunk in chunks:
        yield chunk


def _make_service(chunks: list[str]) -> SynthesiserService:
    """Build a SynthesiserService with a mocked OpenRouter client."""
    mock_client = MagicMock()
    mock_client.stream_completion_iter = lambda _payload: _fake_stream(*chunks)
    return SynthesiserService(client=mock_client)


async def _collect(service: SynthesiserService, **kwargs: Any) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    async for event in service.synthesise(**kwargs):
        events.append(event)
    return events


_BASE = dict(query="Who knows whom?", graph_results=[], graph_context="")


# ---------------------------------------------------------------------------
# text_chunk events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_chunks_emitted():
    chunks = [
        'event: text_chunk\n',
        'data: {"text": "The answer "}\n\n',
        'event: text_chunk\n',
        'data: {"text": "is 42."}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    text_events = [e for e in events if e.event == "text_chunk"]
    assert len(text_events) == 2
    assert text_events[0].data == {"text": "The answer "}
    assert text_events[1].data == {"text": "is 42."}


@pytest.mark.asyncio
async def test_text_chunks_arrive_split_across_chunks():
    """Event boundary falls mid-chunk — buffer must handle it."""
    # Split 'data: ...\n\n' across two raw chunks
    chunks = [
        'event: text_chunk\ndata: {"te',
        'xt": "hello"}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    text_events = [e for e in events if e.event == "text_chunk"]
    assert len(text_events) == 1
    assert text_events[0].data == {"text": "hello"}


# ---------------------------------------------------------------------------
# confidence event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_event_parsed():
    chunks = [
        'event: confidence\ndata: {"score": 0.85, "band": "high"}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    conf = [e for e in events if e.event == "confidence"]
    assert len(conf) == 1
    assert conf[0].data["score"] == 0.85
    assert conf[0].data["band"] == "high"


@pytest.mark.asyncio
async def test_confidence_medium_band():
    chunks = [
        'event: confidence\ndata: {"score": 0.55, "band": "medium"}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    conf = [e for e in events if e.event == "confidence"]
    assert conf[0].data["band"] == "medium"


# ---------------------------------------------------------------------------
# graph_delta event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_delta_emitted():
    chunks = [
        'event: graph_delta\ndata: {"add_nodes": [{"id": "n1", "labels": ["Person"], "properties": {"name": "Alice"}}], "add_edges": []}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    deltas = [e for e in events if e.event == "graph_delta"]
    assert len(deltas) == 1
    assert len(deltas[0].data["add_nodes"]) == 1
    assert deltas[0].data["add_nodes"][0]["id"] == "n1"


# ---------------------------------------------------------------------------
# done event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_done_emitted_at_end():
    chunks = [
        'event: text_chunk\ndata: {"text": "answer"}\n\n',
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    assert events[-1].event == "done"


@pytest.mark.asyncio
async def test_done_added_if_model_omits_it():
    """Synthesiser appends a done event even if the model never emits one."""
    chunks = [
        'event: text_chunk\ndata: {"text": "answer"}\n\n',
        # No done event from the model
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    assert events[-1].event == "done"


@pytest.mark.asyncio
async def test_done_not_duplicated():
    """If model emits done, synthesiser doesn't add a second one."""
    chunks = [
        'event: done\ndata: {}\n\n',
    ]
    service = _make_service(chunks)
    events = await _collect(service, **_BASE)

    done_events = [e for e in events if e.event == "done"]
    assert len(done_events) == 1


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_event_on_stream_exception():
    """On streaming error, yields an error event (no done)."""
    mock_client = MagicMock()

    async def _fail(_payload: Any):
        raise RuntimeError("connection lost")
        yield  # make it an async generator

    mock_client.stream_completion_iter = _fail
    service = SynthesiserService(client=mock_client)

    events = await _collect(service, **_BASE)

    assert len(events) == 1
    assert events[0].event == "error"
    assert "connection lost" in events[0].data["message"]


# ---------------------------------------------------------------------------
# graph_context included
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_context_included_in_call():
    """graph_context is woven into the system prompt (no crash)."""
    chunks = ['event: done\ndata: {}\n\n']
    mock_client = MagicMock()
    captured: list[Any] = []

    async def _capture(payload: Any):
        captured.append(payload)
        yield 'event: done\ndata: {}\n\n'

    mock_client.stream_completion_iter = _capture
    service = SynthesiserService(client=mock_client)

    await _collect(
        service,
        query="test",
        graph_results=[],
        graph_context="Schema: Person -[:KNOWS]-> Person",
    )

    assert captured
    system_msg = captured[0]["messages"][0]["content"]
    assert "Schema: Person" in system_msg


# ---------------------------------------------------------------------------
# _format_graph_results helper
# ---------------------------------------------------------------------------


def test_format_graph_results_empty():
    assert _format_graph_results([]) == "(no graph results)"


def test_format_graph_results_serialises_rows():
    rows = [{"name": "Alice", "age": 30}]
    result = _format_graph_results(rows)
    assert "Alice" in result
    assert "30" in result


def test_format_graph_results_truncates_large():
    big_rows = [{"data": "x" * 200} for _ in range(100)]
    result = _format_graph_results(big_rows)
    assert "truncated" in result
    assert len(result) <= 10_100  # a bit over due to suffix
