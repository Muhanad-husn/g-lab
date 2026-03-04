"""Unit tests for RouterService (intent classification)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.copilot.router import RouterService, _extract_content, _parse_intent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(content: str) -> dict:
    """Build a minimal OpenRouter chat completion response dict."""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    }


def _make_client(response_content: str) -> MagicMock:
    """Return a mock OpenRouterClient that returns *response_content*."""
    client = MagicMock()
    client.chat_completion = AsyncMock(
        return_value=_make_response(response_content)
    )
    return client


# ---------------------------------------------------------------------------
# _extract_content
# ---------------------------------------------------------------------------


def test_extract_content_normal():
    resp = _make_response("hello world")
    assert _extract_content(resp) == "hello world"


def test_extract_content_empty_choices():
    assert _extract_content({"choices": []}) == ""


def test_extract_content_missing_key():
    assert _extract_content({}) == ""


# ---------------------------------------------------------------------------
# _parse_intent
# ---------------------------------------------------------------------------


def test_parse_intent_graph_only():
    raw = json.dumps({"needs_graph": True, "needs_docs": False})
    intent = _parse_intent(raw)
    assert intent.needs_graph is True
    assert intent.needs_docs is False


def test_parse_intent_docs_only():
    raw = json.dumps(
        {"needs_graph": False, "needs_docs": True, "doc_query": "company filings"}
    )
    intent = _parse_intent(raw)
    assert intent.needs_graph is False
    assert intent.needs_docs is True
    assert intent.doc_query == "company filings"


def test_parse_intent_both():
    raw = json.dumps(
        {
            "needs_graph": True,
            "needs_docs": True,
            "cypher_hint": "MATCH (n:Person)",
            "doc_query": "ownership records",
        }
    )
    intent = _parse_intent(raw)
    assert intent.needs_graph is True
    assert intent.needs_docs is True
    assert intent.cypher_hint == "MATCH (n:Person)"
    assert intent.doc_query == "ownership records"


def test_parse_intent_strips_markdown_fences():
    raw = "```json\n" + json.dumps({"needs_graph": True, "needs_docs": False}) + "\n```"
    intent = _parse_intent(raw)
    assert intent.needs_graph is True


def test_parse_intent_fallback_on_invalid_json():
    intent = _parse_intent("not json at all")
    assert intent.needs_graph is True  # fallback
    assert intent.needs_docs is False


def test_parse_intent_empty_string():
    intent = _parse_intent("")
    assert intent.needs_graph is True


# ---------------------------------------------------------------------------
# RouterService.classify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_graph_only():
    payload = json.dumps({"needs_graph": True, "needs_docs": False})
    client = _make_client(payload)
    svc = RouterService(client)

    intent = await svc.classify("Who knows Alice?", graph_context_summary="Person, KNOWS")
    assert intent.needs_graph is True
    assert intent.needs_docs is False
    client.chat_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_classify_docs_only():
    payload = json.dumps(
        {"needs_graph": False, "needs_docs": True, "doc_query": "sanctions list"}
    )
    client = _make_client(payload)
    svc = RouterService(client)

    intent = await svc.classify(
        "Is this company on a sanctions list?",
        graph_context_summary="Company, Person",
    )
    assert intent.needs_graph is False
    assert intent.needs_docs is True
    assert intent.doc_query == "sanctions list"


@pytest.mark.asyncio
async def test_classify_both():
    payload = json.dumps(
        {
            "needs_graph": True,
            "needs_docs": True,
            "cypher_hint": "MATCH (c:Company)",
            "doc_query": "ownership",
        }
    )
    client = _make_client(payload)
    svc = RouterService(client)

    intent = await svc.classify("Show me company ownership", graph_context_summary="")
    assert intent.needs_graph is True
    assert intent.needs_docs is True
    assert intent.cypher_hint == "MATCH (c:Company)"


@pytest.mark.asyncio
async def test_classify_parse_failure_fallback():
    """When the LLM returns garbage, fallback to needs_graph=True."""
    client = _make_client("I cannot determine the intent.")
    svc = RouterService(client)

    intent = await svc.classify("Show me paths between Bob and Carol")
    assert intent.needs_graph is True
    assert intent.needs_docs is False


@pytest.mark.asyncio
async def test_classify_empty_query_fallback():
    """Empty query skips the LLM call entirely and falls back."""
    client = MagicMock()
    client.chat_completion = AsyncMock()
    svc = RouterService(client)

    intent = await svc.classify("   ")
    assert intent.needs_graph is True
    client.chat_completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_classify_llm_error_fallback():
    """When the LLM raises, fallback to needs_graph=True."""
    client = MagicMock()
    client.chat_completion = AsyncMock(side_effect=RuntimeError("network error"))
    svc = RouterService(client)

    intent = await svc.classify("Who are the directors of Acme Corp?")
    assert intent.needs_graph is True


@pytest.mark.asyncio
async def test_classify_sends_schema_in_prompt():
    """Schema summary must appear in the system prompt sent to the LLM."""
    payload = json.dumps({"needs_graph": True, "needs_docs": False})
    client = _make_client(payload)
    svc = RouterService(client)

    schema = "Labels: Person, Company | Rels: KNOWS, OWNS"
    await svc.classify("test query", graph_context_summary=schema)

    call_kwargs = client.chat_completion.call_args.kwargs
    system_msg = call_kwargs["messages"][0]["content"]
    assert schema in system_msg
