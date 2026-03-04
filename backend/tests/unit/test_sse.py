"""Unit tests for app.services.copilot.sse."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.copilot.sse import (
    SSEEvent,
    _parse_sse_block,
    format_sse,
    parse_openrouter_stream,
    parse_sse_buffer,
)

# ---------------------------------------------------------------------------
# format_sse
# ---------------------------------------------------------------------------


def test_format_sse_dict_data():
    event = SSEEvent(event="text_chunk", data={"text": "hello"})
    result = format_sse(event)
    assert result == 'event: text_chunk\ndata: {"text": "hello"}\n\n'


def test_format_sse_empty_dict():
    event = SSEEvent(event="done", data={})
    result = format_sse(event)
    assert result == "event: done\ndata: {}\n\n"


def test_format_sse_string_data():
    event = SSEEvent(event="text_chunk", data="raw text")
    result = format_sse(event)
    assert result == "event: text_chunk\ndata: raw text\n\n"


def test_format_sse_confidence():
    event = SSEEvent(event="confidence", data={"score": 0.85, "band": "high"})
    wire = format_sse(event)
    assert wire.startswith("event: confidence\ndata: ")
    parsed = json.loads(wire.split("data: ", 1)[1].strip())
    assert parsed["score"] == 0.85


# ---------------------------------------------------------------------------
# parse_sse_buffer
# ---------------------------------------------------------------------------


def test_parse_sse_buffer_complete_event():
    buf = 'event: text_chunk\ndata: {"text": "hello"}\n\n'
    events, remaining = parse_sse_buffer(buf)
    assert len(events) == 1
    assert events[0].event == "text_chunk"
    assert events[0].data == {"text": "hello"}
    assert remaining == ""


def test_parse_sse_buffer_incomplete_event():
    buf = 'event: text_chunk\ndata: {"text": "hello"}'
    events, remaining = parse_sse_buffer(buf)
    assert len(events) == 0
    assert remaining == buf


def test_parse_sse_buffer_multiple_events():
    buf = (
        'event: text_chunk\ndata: {"text": "a"}\n\n'
        'event: confidence\ndata: {"score": 0.9, "band": "high"}\n\n'
    )
    events, remaining = parse_sse_buffer(buf)
    assert len(events) == 2
    assert events[0].event == "text_chunk"
    assert events[1].event == "confidence"
    assert remaining == ""


def test_parse_sse_buffer_partial_then_complete():
    """Simulate chunks arriving mid-event."""
    chunk1 = "event: text_chunk\n"
    events1, rem1 = parse_sse_buffer(chunk1)
    assert events1 == []
    assert rem1 == chunk1

    chunk2 = rem1 + 'data: {"text": "hi"}\n\n'
    events2, rem2 = parse_sse_buffer(chunk2)
    assert len(events2) == 1
    assert events2[0].data == {"text": "hi"}
    assert rem2 == ""


def test_parse_sse_buffer_empty_blocks_ignored():
    buf = "\n\n\n\n"
    events, remaining = parse_sse_buffer(buf)
    assert events == []


# ---------------------------------------------------------------------------
# _parse_sse_block
# ---------------------------------------------------------------------------


def test_parse_sse_block_valid():
    block = 'event: done\ndata: {}'
    ev = _parse_sse_block(block)
    assert ev is not None
    assert ev.event == "done"
    assert ev.data == {}


def test_parse_sse_block_missing_event_type():
    block = 'data: {"text": "hello"}'
    assert _parse_sse_block(block) is None


def test_parse_sse_block_missing_data():
    block = "event: done"
    assert _parse_sse_block(block) is None


def test_parse_sse_block_non_json_data():
    block = "event: text_chunk\ndata: not json"
    ev = _parse_sse_block(block)
    assert ev is not None
    assert ev.data == "not json"


# ---------------------------------------------------------------------------
# parse_openrouter_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_openrouter_stream_yields_content():
    lines = [
        'data: {"choices": [{"delta": {"content": "hello"}}]}',
        'data: {"choices": [{"delta": {"content": " world"}}]}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()

    async def fake_aiter_lines():
        for line in lines:
            yield line

    mock_response.aiter_lines = fake_aiter_lines

    chunks = []
    async for chunk in parse_openrouter_stream(mock_response):
        chunks.append(chunk)

    assert chunks == ["hello", " world"]


@pytest.mark.asyncio
async def test_parse_openrouter_stream_skips_empty_content():
    lines = [
        'data: {"choices": [{"delta": {}}]}',
        'data: {"choices": [{"delta": {"content": "text"}}]}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()

    async def fake_aiter_lines():
        for line in lines:
            yield line

    mock_response.aiter_lines = fake_aiter_lines

    chunks = []
    async for chunk in parse_openrouter_stream(mock_response):
        chunks.append(chunk)

    assert chunks == ["text"]


@pytest.mark.asyncio
async def test_parse_openrouter_stream_stops_at_done():
    lines = [
        'data: {"choices": [{"delta": {"content": "a"}}]}',
        "data: [DONE]",
        'data: {"choices": [{"delta": {"content": "b"}}]}',  # after DONE, ignored
    ]

    mock_response = MagicMock()

    async def fake_aiter_lines():
        for line in lines:
            yield line

    mock_response.aiter_lines = fake_aiter_lines

    chunks = []
    async for chunk in parse_openrouter_stream(mock_response):
        chunks.append(chunk)

    assert chunks == ["a"]


@pytest.mark.asyncio
async def test_parse_openrouter_stream_ignores_malformed():
    lines = [
        "not a data line",
        "data: {invalid json}",
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()

    async def fake_aiter_lines():
        for line in lines:
            yield line

    mock_response.aiter_lines = fake_aiter_lines

    chunks = []
    async for chunk in parse_openrouter_stream(mock_response):
        chunks.append(chunk)

    assert chunks == ["ok"]
