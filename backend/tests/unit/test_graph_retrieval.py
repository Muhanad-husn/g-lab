"""Unit tests for GraphRetrievalService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import RouterIntent
from app.services.copilot.graph_retrieval import (
    GraphRetrievalService,
    _clean_cypher_text,
    _rows_to_evidence,
)
from app.utils.exceptions import CypherValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _make_intent(
    needs_graph: bool = True,
    cypher_hint: str | None = None,
) -> RouterIntent:
    return RouterIntent(
        needs_graph=needs_graph,
        needs_docs=False,
        cypher_hint=cypher_hint,
    )


def _make_service() -> tuple[GraphRetrievalService, AsyncMock]:
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return GraphRetrievalService(client), client


def _make_neo4j(rows: list[dict] | None = None) -> AsyncMock:
    svc = MagicMock()
    svc.execute_raw = AsyncMock(return_value=rows or [])
    return svc


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_success() -> None:
    """Happy path: LLM produces valid Cypher, execution returns rows."""
    service, client = _make_service()
    cypher = "MATCH (n:Person) RETURN n.name AS name LIMIT 10"
    client.chat_completion.return_value = _make_llm_response(cypher)

    rows = [{"name": "Alice"}, {"name": "Bob"}]
    neo4j = _make_neo4j(rows)

    intent = _make_intent(needs_graph=True)
    result_rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert result_rows == rows
    assert len(evidence) == 2
    assert evidence[0].type == "graph_path"
    assert evidence[0].id == "row_0"
    assert "Alice" in evidence[0].content


@pytest.mark.asyncio
async def test_retrieve_skipped_when_needs_graph_false() -> None:
    """If intent.needs_graph is False, return empty immediately."""
    service, client = _make_service()
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=False)
    rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []
    client.chat_completion.assert_not_called()
    neo4j.execute_raw.assert_not_called()


# ---------------------------------------------------------------------------
# Sanitiser reject + retry success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_sanitiser_reject_then_retry_success() -> None:
    """First query rejected, retry produces valid Cypher."""
    service, client = _make_service()

    bad_cypher = "CREATE (n:Bad) RETURN n"
    good_cypher = "MATCH (n:Person) RETURN n.name LIMIT 10"

    # First call returns bad Cypher, second (retry) returns good Cypher
    client.chat_completion.side_effect = [
        _make_llm_response(bad_cypher),
        _make_llm_response(good_cypher),
    ]

    rows = [{"n.name": "Alice"}]
    neo4j = _make_neo4j(rows)

    intent = _make_intent(needs_graph=True)
    result_rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert result_rows == rows
    assert len(evidence) == 1
    assert client.chat_completion.call_count == 2


# ---------------------------------------------------------------------------
# Double rejection → empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_double_rejection_returns_empty() -> None:
    """Both queries rejected by sanitiser → empty results, no execution."""
    service, client = _make_service()

    bad1 = "CREATE (n:X) RETURN n"
    bad2 = "MERGE (n:Y) RETURN n"

    client.chat_completion.side_effect = [
        _make_llm_response(bad1),
        _make_llm_response(bad2),
    ]
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=True)
    rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []
    neo4j.execute_raw.assert_not_called()


# ---------------------------------------------------------------------------
# Execution timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_execution_timeout_returns_empty() -> None:
    """If execute_raw times out, return empty results gracefully."""
    import asyncio

    service, client = _make_service()
    cypher = "MATCH (n) RETURN n LIMIT 50"
    client.chat_completion.return_value = _make_llm_response(cypher)

    neo4j = MagicMock()

    async def _slow(*_args: object, **_kwargs: object) -> list:
        await asyncio.sleep(100)
        return []

    neo4j.execute_raw = _slow

    intent = _make_intent(needs_graph=True)

    # Patch timeout to 0.01s so the test is fast
    with patch(
        "app.services.copilot.graph_retrieval._EXECUTE_TIMEOUT_S", 0.01
    ):
        rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []


# ---------------------------------------------------------------------------
# LLM error on first call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_llm_error_returns_empty() -> None:
    """If the LLM call raises, return empty without crashing."""
    service, client = _make_service()
    client.chat_completion.side_effect = RuntimeError("network error")
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=True)
    rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []
    neo4j.execute_raw.assert_not_called()


# ---------------------------------------------------------------------------
# LLM error on retry call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_retry_llm_error_returns_empty() -> None:
    """First query rejected, retry LLM call fails → empty results."""
    service, client = _make_service()

    bad_cypher = "DELETE (n) RETURN n"
    client.chat_completion.side_effect = [
        _make_llm_response(bad_cypher),
        RuntimeError("retry network error"),
    ]
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=True)
    rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []
    neo4j.execute_raw.assert_not_called()


# ---------------------------------------------------------------------------
# Markdown-fenced Cypher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_strips_markdown_fences() -> None:
    """LLM wraps query in markdown fences — should still work."""
    service, client = _make_service()
    cypher = "MATCH (n:Person) RETURN n.name LIMIT 5"
    fenced = f"```cypher\n{cypher}\n```"
    client.chat_completion.return_value = _make_llm_response(fenced)

    rows = [{"n.name": "Eve"}]
    neo4j = _make_neo4j(rows)

    intent = _make_intent(needs_graph=True)
    result_rows, evidence = await service.retrieve(intent, "schema...", neo4j)

    assert result_rows == rows
    assert len(evidence) == 1


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


def test_clean_cypher_text_strips_fences() -> None:
    raw = "```cypher\nMATCH (n) RETURN n\n```"
    assert _clean_cypher_text(raw) == "MATCH (n) RETURN n"


def test_clean_cypher_text_no_fences() -> None:
    raw = "  MATCH (n) RETURN n  "
    assert _clean_cypher_text(raw) == "MATCH (n) RETURN n"


def test_rows_to_evidence_basic() -> None:
    rows = [{"name": "Alice", "age": 30}]
    evidence = _rows_to_evidence(rows)
    assert len(evidence) == 1
    assert evidence[0].id == "row_0"
    assert "Alice" in evidence[0].content


def test_rows_to_evidence_caps_at_20() -> None:
    rows = [{"v": i} for i in range(25)]
    evidence = _rows_to_evidence(rows)
    assert len(evidence) == 20


def test_rows_to_evidence_empty() -> None:
    assert _rows_to_evidence([]) == []
