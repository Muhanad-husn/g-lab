"""Unit tests for GraphRetrievalService — tool-based dispatch."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import RouterIntent
from app.services.copilot.graph_retrieval import (
    GraphRetrievalService,
    ToolCall,
    _clean_cypher_text,
    _interleave_path,
    _normalize_expand,
    _normalize_paths,
    _normalize_search,
    _parse_tool_call,
    _rows_to_evidence,
)

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


def _make_neo4j() -> MagicMock:
    svc = MagicMock()
    svc.search = AsyncMock(return_value=[])
    svc.expand = AsyncMock(return_value=([], []))
    svc.find_paths = AsyncMock(return_value=([], [], []))
    svc.execute_raw = AsyncMock(return_value=[])
    return svc


# ---------------------------------------------------------------------------
# _parse_tool_call
# ---------------------------------------------------------------------------


def test_parse_tool_call_valid_json() -> None:
    text = '{"tool": "search", "params": {"query": "Alice", "limit": 10}}'
    tc = _parse_tool_call(text)
    assert tc is not None
    assert tc.tool == "search"
    assert tc.params["query"] == "Alice"


def test_parse_tool_call_with_markdown_fences() -> None:
    text = '```json\n{"tool": "expand", "params": {"node_ids": ["4:abc:1"]}}\n```'
    tc = _parse_tool_call(text)
    assert tc is not None
    assert tc.tool == "expand"


def test_parse_tool_call_raw_cypher_fallback() -> None:
    text = "MATCH (n:Person) RETURN n LIMIT 10"
    tc = _parse_tool_call(text)
    assert tc is not None
    assert tc.tool == "cypher"
    assert tc.params["query"] == text


def test_parse_tool_call_invalid_returns_none() -> None:
    assert _parse_tool_call("I don't know what to do") is None


def test_parse_tool_call_find_paths() -> None:
    text = json.dumps(
        {
            "tool": "find_paths",
            "params": {
                "source_id": "4:abc:1",
                "target_id": "4:abc:2",
                "max_hops": 3,
                "mode": "shortest",
            },
        }
    )
    tc = _parse_tool_call(text)
    assert tc is not None
    assert tc.tool == "find_paths"
    assert tc.params["source_id"] == "4:abc:1"


# ---------------------------------------------------------------------------
# Normalizer functions
# ---------------------------------------------------------------------------


def test_normalize_search() -> None:
    nodes = [
        {
            "id": "4:abc:1",
            "labels": ["Person"],
            "properties": {"name": "Alice", "age": 30},
        },
        {
            "id": "4:abc:2",
            "labels": ["Organization"],
            "properties": {"name": "Acme Corp"},
        },
    ]
    rows = _normalize_search(nodes)
    assert len(rows) == 2
    assert rows[0]["id"] == "4:abc:1"
    assert rows[0]["labels"] == ["Person"]
    assert rows[0]["name"] == "Alice"
    assert rows[0]["age"] == 30


def test_normalize_expand() -> None:
    nodes = [
        {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "Alice"}},
        {"id": "4:abc:2", "labels": ["Company"], "properties": {"name": "Acme"}},
    ]
    edges = [
        {
            "id": "5:abc:10",
            "type": "WORKS_FOR",
            "source": "4:abc:1",
            "target": "4:abc:2",
            "properties": {},
        }
    ]
    rows = _normalize_expand(nodes, edges)
    assert len(rows) == 1
    assert rows[0]["source_name"] == "Alice"
    assert rows[0]["relationship"] == "WORKS_FOR"
    assert rows[0]["target_name"] == "Acme"


def test_normalize_paths() -> None:
    """Path elements from find_paths: nodes first, then edges."""
    path = [
        {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "A"}},
        {"id": "4:abc:2", "labels": ["Org"], "properties": {"name": "B"}},
        {"id": "4:abc:3", "labels": ["Person"], "properties": {"name": "C"}},
        {
            "id": "5:abc:10",
            "type": "WORKS_FOR",
            "source": "4:abc:1",
            "target": "4:abc:2",
            "properties": {},
        },
        {
            "id": "5:abc:11",
            "type": "EMPLOYS",
            "source": "4:abc:2",
            "target": "4:abc:3",
            "properties": {},
        },
    ]
    rows = _normalize_paths([path])
    assert len(rows) == 1
    p = rows[0]["p"]
    # Should be interleaved: node, edge, node, edge, node
    assert len(p) == 5
    assert "labels" in p[0]  # node
    assert "type" in p[1]  # edge
    assert "labels" in p[2]  # node
    assert "type" in p[3]  # edge
    assert "labels" in p[4]  # node


def test_normalize_paths_empty() -> None:
    assert _normalize_paths([]) == []
    assert _normalize_paths([[]]) == []


# ---------------------------------------------------------------------------
# _interleave_path
# ---------------------------------------------------------------------------


def test_interleave_path_simple() -> None:
    nodes = [
        {"id": "a", "labels": ["X"], "properties": {"name": "A"}},
        {"id": "b", "labels": ["Y"], "properties": {"name": "B"}},
    ]
    edges = [
        {"id": "e1", "type": "REL", "source": "a", "target": "b", "properties": {}},
    ]
    result = _interleave_path(nodes, edges)
    assert len(result) == 3
    assert result[0]["id"] == "a"
    assert result[1]["type"] == "REL"
    assert result[2]["id"] == "b"


def test_interleave_path_no_edges() -> None:
    nodes = [{"id": "a", "labels": ["X"], "properties": {}}]
    result = _interleave_path(nodes, [])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Retrieve — tool dispatch integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_search_tool() -> None:
    """LLM selects search tool → dispatches to neo4j_service.search()."""
    service, client = _make_service()
    tool_json = json.dumps(
        {"tool": "search", "params": {"query": "Alice", "limit": 10}}
    )
    # First call: entity extraction returns []
    # Second call: tool selection returns search tool
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
    ]
    neo4j = _make_neo4j()
    neo4j.search.return_value = [
        {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "Alice"}}
    ]

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="find Alice"
    )

    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"
    assert len(evidence) == 1
    assert json.loads(tool_info)["tool"] == "search"
    neo4j.search.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_find_paths_tool() -> None:
    """LLM selects find_paths → dispatches to neo4j_service.find_paths()."""
    service, client = _make_service()
    tool_json = json.dumps(
        {
            "tool": "find_paths",
            "params": {
                "source_id": "4:abc:1",
                "target_id": "4:abc:2",
                "max_hops": 3,
            },
        }
    )
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
    ]

    # find_paths returns (paths, nodes, edges)
    path = [
        {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "A"}},
        {"id": "4:abc:2", "labels": ["Person"], "properties": {"name": "B"}},
        {
            "id": "5:abc:10",
            "type": "KNOWS",
            "source": "4:abc:1",
            "target": "4:abc:2",
            "properties": {},
        },
    ]
    neo4j = _make_neo4j()
    neo4j.find_paths.return_value = ([path], [], [])

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="how are A and B connected?"
    )

    assert len(rows) == 1
    assert "p" in rows[0]  # path format
    assert json.loads(tool_info)["tool"] == "find_paths"
    neo4j.find_paths.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_expand_tool() -> None:
    """LLM selects expand → dispatches to neo4j_service.expand()."""
    service, client = _make_service()
    tool_json = json.dumps(
        {"tool": "expand", "params": {"node_ids": ["4:abc:1"], "hops": 2, "limit": 25}}
    )
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
    ]

    nodes = [
        {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "Alice"}},
        {"id": "4:abc:2", "labels": ["Company"], "properties": {"name": "Acme"}},
    ]
    edges = [
        {
            "id": "5:abc:10",
            "type": "WORKS_FOR",
            "source": "4:abc:1",
            "target": "4:abc:2",
            "properties": {},
        }
    ]
    neo4j = _make_neo4j()
    neo4j.expand.return_value = (nodes, edges)

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="who is connected to Alice?"
    )

    assert len(rows) == 1
    assert rows[0]["relationship"] == "WORKS_FOR"
    assert json.loads(tool_info)["tool"] == "expand"
    neo4j.expand.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_cypher_fallback_tool() -> None:
    """LLM selects cypher tool → sanitises + dispatches to execute_raw."""
    service, client = _make_service()
    cypher = "MATCH (n:Person) RETURN count(n) AS total"
    tool_json = json.dumps({"tool": "cypher", "params": {"query": cypher}})
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
    ]
    neo4j = _make_neo4j()
    neo4j.execute_raw.return_value = [{"total": 42}]

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="how many people?"
    )

    assert rows == [{"total": 42}]
    assert json.loads(tool_info)["tool"] == "cypher"
    neo4j.execute_raw.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_skipped_when_needs_graph_false() -> None:
    """If intent.needs_graph is False, return empty immediately."""
    service, client = _make_service()
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=False)
    rows, evidence, tool_info = await service.retrieve(intent, "schema...", neo4j)

    assert rows == []
    assert evidence == []
    assert tool_info == ""
    client.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_raw_cypher_from_llm_parsed_as_cypher_tool() -> None:
    """If LLM outputs raw MATCH instead of JSON, fallback wraps as cypher tool."""
    service, client = _make_service()
    raw_cypher = "MATCH (n:Person) RETURN n.name LIMIT 10"
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(raw_cypher),  # raw Cypher instead of JSON
    ]
    neo4j = _make_neo4j()
    neo4j.execute_raw.return_value = [{"n.name": "Alice"}]

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="find people"
    )

    assert len(rows) == 1
    assert json.loads(tool_info)["tool"] == "cypher"


@pytest.mark.asyncio
async def test_retrieve_empty_results_triggers_retry() -> None:
    """Empty results from first dispatch triggers a retry with different tool."""
    service, client = _make_service()

    # First tool: search with no results, retry: cypher with results
    search_json = json.dumps(
        {"tool": "search", "params": {"query": "nobody", "limit": 10}}
    )
    cypher_json = json.dumps(
        {"tool": "cypher", "params": {"query": "MATCH (n) RETURN n LIMIT 5"}}
    )
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),  # entity extraction
        _make_llm_response(search_json),  # tool selection
        _make_llm_response(cypher_json),  # retry tool selection
    ]
    neo4j = _make_neo4j()
    neo4j.search.return_value = []  # empty results trigger retry
    neo4j.execute_raw.return_value = [{"n": "something"}]

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="find nobody"
    )

    assert len(rows) == 1
    assert json.loads(tool_info)["tool"] == "cypher"
    # 3 LLM calls: entity extraction + tool selection + retry
    assert client.chat_completion.call_count == 3


@pytest.mark.asyncio
async def test_retrieve_llm_error_returns_empty() -> None:
    """If the LLM call raises, return empty without crashing."""
    service, client = _make_service()
    client.chat_completion.side_effect = RuntimeError("network error")
    neo4j = _make_neo4j()

    intent = _make_intent(needs_graph=True)
    rows, evidence, tool_info = await service.retrieve(
        intent, "schema...", neo4j, query="test"
    )

    assert rows == []
    assert evidence == []
    assert tool_info == ""


@pytest.mark.asyncio
async def test_retrieve_dispatch_timeout() -> None:
    """If dispatch times out, return empty results gracefully."""
    import asyncio as _asyncio

    service, client = _make_service()
    tool_json = json.dumps(
        {"tool": "search", "params": {"query": "slow", "limit": 10}}
    )
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
        _make_llm_response(tool_json),  # retry also times out
    ]

    neo4j = _make_neo4j()

    async def _slow(*_args: object, **_kwargs: object) -> list:
        await _asyncio.sleep(100)
        return []

    neo4j.search = _slow

    intent = _make_intent(needs_graph=True)

    with patch(
        "app.services.copilot.graph_retrieval._EXECUTE_TIMEOUT_S", 0.01
    ):
        rows, evidence, tool_info = await service.retrieve(
            intent, "schema...", neo4j, query="slow query"
        )

    assert rows == []
    assert evidence == []


@pytest.mark.asyncio
async def test_retrieve_guardrail_caps_hops() -> None:
    """Dispatch caps hops at _MAX_HOPS (5)."""
    service, client = _make_service()
    tool_json = json.dumps(
        {
            "tool": "expand",
            "params": {"node_ids": ["4:abc:1"], "hops": 99, "limit": 999},
        }
    )
    client.chat_completion.side_effect = [
        _make_llm_response("[]"),
        _make_llm_response(tool_json),
    ]
    neo4j = _make_neo4j()
    neo4j.expand.return_value = ([], [])

    intent = _make_intent(needs_graph=True)
    await service.retrieve(intent, "schema...", neo4j, query="test")

    # Verify hops was capped to 5, limit to 100
    call_kwargs = neo4j.expand.call_args
    assert call_kwargs.kwargs.get("hops", call_kwargs[1].get("hops")) <= 5
    assert call_kwargs.kwargs.get("limit", call_kwargs[1].get("limit")) <= 100


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
