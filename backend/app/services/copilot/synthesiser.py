"""Copilot synthesiser service.

Streams the final answer as a sequence of typed SSE events:
``text_chunk``, ``evidence``, ``graph_delta``, ``confidence``, ``done``.

The LLM is prompted (via SYNTHESISER_SYSTEM_PROMPT) to produce
SSE-formatted text.  This service buffers the streaming output and
parses it into :class:`~app.services.copilot.sse.SSEEvent` objects as
they arrive.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import DocumentChunk
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.prompts import SYNTHESISER_SYSTEM_PROMPT
from app.services.copilot.sse import SSEEvent, parse_sse_buffer

logger: Any = get_logger(__name__)

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
_MAX_GRAPH_RESULTS_CHARS = 10_000


class SynthesiserService:
    """Stream an answer from graph results as a sequence of SSE events."""

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    def synthesise(
        self,
        query: str,
        graph_results: list[dict[str, Any]],
        graph_context: str,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = True,
        doc_chunks: list[DocumentChunk] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        context_window_tokens: int = 128_000,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Return an async generator that yields typed SSE events.

        Callers use ``async for event in service.synthesise(...)``.

        Args:
            query: The original user query.
            graph_results: Raw row dicts from graph retrieval (may be empty).
            graph_context: Optional additional context (e.g. schema summary).
            model: OpenRouter model ID.
            temperature: Sampling temperature.
            max_tokens: Token budget for the answer.
            stream: Reserved; streaming is always used.
            doc_chunks: Optional document chunks from vector search + reranking.
            conversation_history: Prior user/assistant message pairs.
            context_window_tokens: Model context window size for budget calc.

        Returns:
            Async generator yielding :class:`SSEEvent` objects in order:
            zero or more ``text_chunk``, then ``evidence``, optionally
            ``graph_delta``, then ``confidence``, then ``done``.
            On error, yields a single ``error`` event.
        """
        return self._stream(
            query=query,
            graph_results=graph_results,
            graph_context=graph_context,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            doc_chunks=doc_chunks or [],
            conversation_history=conversation_history,
            context_window_tokens=context_window_tokens,
        )

    async def _stream(
        self,
        query: str,
        graph_results: list[dict[str, Any]],
        graph_context: str,
        model: str,
        temperature: float,
        max_tokens: int,
        doc_chunks: list[DocumentChunk] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        context_window_tokens: int = 128_000,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Internal async generator — yields typed SSE events."""
        # Build conversation history text for the prompt
        history_text = "(no prior conversation)"
        trimmed_history: list[dict[str, str]] = []
        was_trimmed = False
        messages_total = 0

        if conversation_history:
            messages_total = len(conversation_history)
            budget_tokens = int(context_window_tokens * 0.75)
            trimmed_history, was_trimmed, _included, _ = _trim_history(
                conversation_history, budget_tokens
            )
            if trimmed_history:
                lines: list[str] = []
                for msg in trimmed_history:
                    role_label = "User" if msg["role"] == "user" else "Assistant"
                    lines.append(f"{role_label}: {msg['content']}")
                history_text = "\n\n".join(lines)

        system_prompt = SYNTHESISER_SYSTEM_PROMPT.format(
            graph_results=_format_graph_results(graph_results),
            doc_context=_format_doc_chunks(doc_chunks or []),
            conversation_history=history_text,
            query=query,
        )
        if graph_context:
            system_prompt = f"Graph context:\n{graph_context}\n\n{system_prompt}"

        # Emit context_warning before synthesis if history was trimmed
        if was_trimmed:
            included = len(trimmed_history)
            yield SSEEvent(
                event="context_warning",
                data={
                    "messages_included": included,
                    "messages_total": messages_total,
                },
            )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        buffer = ""
        emitted_done = False

        try:
            async for chunk in self._client.stream_completion_iter(payload):
                buffer += chunk
                events, buffer = parse_sse_buffer(buffer)
                for event in events:
                    yield event
                    if event.event == "done":
                        emitted_done = True

            # Flush any remaining buffered content (force-close the last block)
            if buffer.strip():
                events, _ = parse_sse_buffer(buffer + "\n\n")
                for event in events:
                    yield event
                    if event.event == "done":
                        emitted_done = True

        except Exception as exc:
            logger.warning("synthesiser_stream_error", error=str(exc))
            yield SSEEvent(event="error", data={"message": str(exc)})
            return

        if not emitted_done:
            yield SSEEvent(event="done", data={})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length (~4 chars per token)."""
    return len(text) // 4


def _trim_history(
    messages: list[dict[str, str]],
    budget_tokens: int,
) -> tuple[list[dict[str, str]], bool, int, int]:
    """Trim conversation history to fit within a token budget.

    Walks backwards through messages, keeping complete user/assistant pairs
    that fit within the budget.

    Returns:
        (trimmed_messages, was_trimmed, messages_included, messages_total)
    """
    total = len(messages)
    if not messages:
        return [], False, 0, 0

    used = 0
    keep_from = total  # index to slice from

    # Walk backwards, keeping complete pairs
    i = total - 1
    while i >= 0:
        msg_tokens = _estimate_tokens(messages[i]["content"])
        # Try to keep pairs: if this is an assistant msg, also grab the user msg before it
        if i > 0 and messages[i]["role"] == "assistant" and messages[i - 1]["role"] == "user":
            pair_tokens = msg_tokens + _estimate_tokens(messages[i - 1]["content"])
            if used + pair_tokens > budget_tokens:
                break
            used += pair_tokens
            keep_from = i - 1
            i -= 2
        else:
            if used + msg_tokens > budget_tokens:
                break
            used += msg_tokens
            keep_from = i
            i -= 1

    trimmed = messages[keep_from:]
    included = len(trimmed)
    was_trimmed = included < total
    return trimmed, was_trimmed, included, total


def _format_doc_chunks(chunks: list[DocumentChunk]) -> str:
    """Serialise document chunks for inclusion in the synthesiser prompt."""
    if not chunks:
        return "(no document context)"
    lines: list[str] = []
    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        header_parts: list[str] = [f"[{i + 1}]", f"doc_id={meta.document_id}"]
        if meta.page_number is not None:
            header_parts.append(f"page={meta.page_number}")
        if meta.section_heading:
            header_parts.append(f"section={meta.section_heading!r}")
        header_parts.append(f"tier={meta.parse_tier}")
        header_parts.append(f"chunk_id={chunk.id}")
        lines.append(" ".join(header_parts))
        lines.append(chunk.text[:500])
        lines.append("")
    return "\n".join(lines).strip()


def _is_path(value: Any) -> bool:
    """Return True if *value* looks like a Neo4j path (alternating nodes/edges)."""
    if not isinstance(value, list) or len(value) < 3:
        return False
    # Even-indexed items should be nodes (have "labels"),
    # odd-indexed items should be edges (have "type").
    for i, elem in enumerate(value):
        if not isinstance(elem, dict):
            return False
        if i % 2 == 0:
            if "labels" not in elem:
                return False
        else:
            if "type" not in elem:
                return False
    return True


def _node_display(node: dict[str, Any]) -> str:
    """Format a node dict as ``(name [Label])``."""
    props = node.get("properties", {})
    name = (
        props.get("name")
        or props.get("title")
        or props.get("_primary_value")
        or node.get("id", "?")
    )
    labels = node.get("labels", [])
    label_str = labels[0] if labels else "?"
    return f"({name} [{label_str}])"


def _format_edge_props(props: dict[str, Any]) -> str:
    """Format edge properties as a compact key=value string, skipping internals."""
    skip = {"_dedupe_key", "_run_id", "_chunk_id", "_schema_version", "_created_at"}
    pairs = [
        f"{k}={v}"
        for k, v in props.items()
        if k not in skip and v is not None and str(v).strip()
    ]
    return ", ".join(pairs)


def _format_path(path: list[dict[str, Any]]) -> str:
    """Convert an alternating node/edge list into a human-readable string."""
    parts: list[str] = []
    for i, elem in enumerate(path):
        if i % 2 == 0:
            parts.append(_node_display(elem))
        else:
            rel_type = elem.get("type", "RELATED_TO")
            props = elem.get("properties", {})
            prop_str = _format_edge_props(props)
            if prop_str:
                parts.append(f"-[{rel_type} {{ {prop_str} }}]->")
            else:
                parts.append(f"-[{rel_type}]->")
    return "Path: " + " ".join(parts)


def _format_graph_results(rows: list[dict[str, Any]]) -> str:
    """Serialise graph rows for inclusion in the prompt."""
    if not rows:
        return "(no graph results)"
    formatted_rows: list[dict[str, Any]] = []
    for row in rows[:50]:
        formatted: dict[str, Any] = {}
        for k, v in row.items():
            if _is_path(v):
                formatted[k] = _format_path(v)
            else:
                formatted[k] = v
        formatted_rows.append(formatted)
    text = json.dumps(formatted_rows, default=str)
    if len(text) > _MAX_GRAPH_RESULTS_CHARS:
        text = text[:_MAX_GRAPH_RESULTS_CHARS] + "... (truncated)"
    return text
