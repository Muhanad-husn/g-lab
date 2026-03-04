"""SSE (Server-Sent Events) utilities for the Copilot pipeline.

Provides:
- SSEEvent dataclass
- format_sse() — wire-format serialisation
- parse_openrouter_stream() — content extractor for raw OpenRouter SSE responses
- parse_sse_buffer() — incremental parser for LLM-generated SSE text
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.logging import get_logger

logger: Any = get_logger(__name__)


@dataclass
class SSEEvent:
    """A single typed SSE event."""

    event: str
    data: dict[str, Any] | str = field(default_factory=dict)


def format_sse(event: SSEEvent) -> str:
    """Serialise an SSEEvent to wire-format SSE text.

    Example output::

        event: text_chunk
        data: {"text": "hello"}

    (trailing blank line included)
    """
    if isinstance(event.data, dict):
        data_str = json.dumps(event.data)
    else:
        data_str = str(event.data)
    return f"event: {event.event}\ndata: {data_str}\n\n"


async def parse_openrouter_stream(
    response: httpx.Response,
) -> AsyncGenerator[str, None]:
    """Parse the raw OpenRouter SSE response and yield content text chunks.

    Handles the ``data: [DONE]`` terminator and skips non-content lines.
    Intended for use inside an ``async with client.stream(...)`` block.

    Args:
        response: A streaming ``httpx.Response`` in an active stream context.

    Yields:
        Content strings extracted from ``choices[0].delta.content``.
    """
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            return
        try:
            chunk = json.loads(data_str)
            choices = chunk.get("choices", [])
            if not choices:
                continue
            content = (choices[0].get("delta") or {}).get("content") or ""
            if content:
                yield content
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass


def parse_sse_buffer(buffer: str) -> tuple[list[SSEEvent], str]:
    """Parse complete SSE events from an accumulation buffer.

    Splits on ``\\n\\n`` (event separator).  Incomplete trailing data is
    returned as the second element so the caller can prepend it to the
    next incoming chunk.

    Args:
        buffer: Text accumulated from streaming LLM output.

    Returns:
        ``(events, remaining)`` where *events* is a list of fully-parsed
        :class:`SSEEvent` objects and *remaining* is any incomplete suffix.
    """
    events: list[SSEEvent] = []
    parts = buffer.split("\n\n")
    remaining = parts[-1]  # may be empty string or incomplete block
    for block in parts[:-1]:
        block = block.strip()
        if not block:
            continue
        ev = _parse_sse_block(block)
        if ev is not None:
            events.append(ev)
    return events, remaining


def _parse_sse_block(block: str) -> SSEEvent | None:
    """Parse a single ``event: ...\\ndata: ...`` block into an SSEEvent.

    Returns ``None`` if the block is missing an event type or data line.
    """
    event_type: str | None = None
    data_str: str | None = None
    for line in block.splitlines():
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_str = line[5:].strip()
    if not event_type or data_str is None:
        return None
    try:
        data: dict[str, Any] | str = json.loads(data_str)
    except json.JSONDecodeError:
        data = data_str
    return SSEEvent(event=event_type, data=data)
