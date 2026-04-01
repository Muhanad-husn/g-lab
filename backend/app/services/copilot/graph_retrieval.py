"""Copilot graph retrieval service.

Resolves entity names from the user query against the actual graph database,
then selects a structured tool (search / expand / find_paths / cypher fallback),
dispatches to the appropriate Neo4jService method, and maps results to
EvidenceSource objects.

Flow: extract entities → search Neo4j → select tool → dispatch → normalise.
Retries once if the selected tool fails.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from pydantic import BaseModel

from app.core.logging import get_logger
from app.models.schemas import EvidenceSource, RouterIntent
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.prompts import (
    ENTITY_EXTRACTION_PROMPT,
    GRAPH_RETRIEVAL_RETRY_PROMPT,
    GRAPH_RETRIEVAL_SYSTEM_PROMPT,
    GRAPH_TOOL_RETRY_PROMPT,
    GRAPH_TOOL_SELECTION_PROMPT,
)
from app.utils.cypher import CypherSanitiser
from app.utils.exceptions import CypherValidationError

logger: Any = get_logger(__name__)

_SANITISER = CypherSanitiser()
_EXECUTE_TIMEOUT_S = 30.0
_ENTITY_SEARCH_LIMIT = 5  # max results per entity name

# Guardrail caps applied during dispatch
_MAX_HOPS = 5
_MAX_LIMIT = 100


class ToolCall(BaseModel):
    """Structured tool selection from the LLM."""

    tool: Literal["search", "expand", "find_paths", "cypher"]
    params: dict[str, Any]


class GraphRetrievalService:
    """Select a graph tool and dispatch to Neo4jService methods."""

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    async def retrieve(
        self,
        intent: RouterIntent,
        schema_summary: str,
        neo4j_service: Any,
        model: str = "anthropic/claude-haiku-4-5",
        temperature: float = 0.0,
        max_tokens: int = 512,
        query: str = "",
    ) -> tuple[list[dict[str, Any]], list[EvidenceSource], str]:
        """Select a tool, dispatch, and return raw rows + evidence + tool info.

        Returns ``([], [], "")`` on skip, failure, or timeout.
        """
        if not intent.needs_graph:
            logger.debug("graph_retrieval_skipped", reason="needs_graph=False")
            return [], [], ""

        # --- Step 1: resolve entities from the query ---
        resolved = await self._resolve_entities(
            query=query,
            neo4j_service=neo4j_service,
            model=model,
        )

        # --- Step 2: select tool ---
        tool_call = await self._select_tool(
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            query=query,
            resolved_entities=resolved,
        )
        if not tool_call:
            return [], [], ""

        # --- Step 3: dispatch with retry ---
        rows, tool_info = await self._dispatch_with_retry(
            tool_call=tool_call,
            neo4j_service=neo4j_service,
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            query=query,
            resolved_entities=resolved,
        )

        # --- Step 4: map to evidence sources ---
        evidence = _rows_to_evidence(rows)

        logger.debug(
            "graph_retrieval_complete",
            row_count=len(rows),
            evidence_count=len(evidence),
            tool=tool_call.tool,
        )
        return rows, evidence, tool_info

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------

    async def _resolve_entities(
        self,
        query: str,
        neo4j_service: Any,
        model: str,
    ) -> str:
        """Extract entity names from the query and search Neo4j for matches.

        Returns a formatted string of resolved entities for the tool prompt.
        """
        if not query:
            return "(no entities)"

        # Ask LLM to extract entity names
        names = await self._extract_entity_names(query, model)
        if not names:
            return "(no entities detected)"

        logger.debug("entity_extraction", names=names)

        # Search Neo4j for each entity name in parallel
        search_tasks = [self._search_entity(name, neo4j_service) for name in names]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Format results
        lines: list[str] = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, Exception):
                lines.append(f'"{name}": (search failed)')
                continue
            if not result:
                lines.append(f'"{name}": (not found in database)')
                continue
            for node in result:
                node_id = node.get("id", "?")
                labels = node.get("labels", [])
                props = node.get("properties", {})
                # Show key properties for matching
                prop_str = ", ".join(f"{k}={v!r}" for k, v in list(props.items())[:5])
                lines.append(
                    f'"{name}" → elementId={node_id!r}, labels={labels}, {prop_str}'
                )
        return "\n".join(lines) if lines else "(no entities resolved)"

    async def _extract_entity_names(self, query: str, model: str) -> list[str]:
        """Use the LLM to extract entity names from the user query."""
        messages = [
            {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
            {"role": "user", "content": query},
        ]
        try:
            response = await self._client.chat_completion(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=128,
                stream=False,
            )
        except Exception as exc:
            logger.warning("entity_extraction_llm_error", error=str(exc))
            return []

        content = _extract_content(response)
        return _parse_entity_names(content)

    async def _search_entity(
        self, name: str, neo4j_service: Any
    ) -> list[dict[str, Any]]:
        """Search Neo4j for nodes matching an entity name."""
        try:
            results: list[dict[str, Any]] = await asyncio.wait_for(
                neo4j_service.search(
                    query=name, labels=None, limit=_ENTITY_SEARCH_LIMIT
                ),
                timeout=10.0,
            )
            return results
        except Exception as exc:
            logger.warning("entity_search_error", name=name, error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    async def _select_tool(
        self,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> ToolCall | None:
        """Ask the LLM to pick a tool and structured params."""
        system_prompt = GRAPH_TOOL_SELECTION_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            resolved_entities=resolved_entities or "(none)",
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent, query)},
        ]
        try:
            response = await self._client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.warning("tool_selection_llm_error", error=str(exc))
            return None

        content = _extract_content(response)
        return _parse_tool_call(content)

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _dispatch_with_retry(
        self,
        tool_call: ToolCall,
        neo4j_service: Any,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        """Dispatch tool_call; retry once with a different tool on failure."""
        rows, tool_info, error = await self._dispatch_tool(tool_call, neo4j_service)
        if error is None and rows:
            return rows, tool_info

        # First attempt returned empty or errored — retry with LLM guidance
        error_reason = error or "Query returned no results"
        logger.warning(
            "tool_dispatch_retry",
            tool=tool_call.tool,
            reason=error_reason,
        )

        retry_tool = await self._retry_tool_selection(
            original_tool=tool_call,
            error_reason=error_reason,
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            query=query,
            resolved_entities=resolved_entities,
        )
        if not retry_tool:
            # Return whatever we got from the first attempt (may be empty)
            return rows, tool_info

        retry_rows, retry_info, retry_error = await self._dispatch_tool(
            retry_tool, neo4j_service
        )
        if retry_error is not None:
            logger.warning(
                "tool_dispatch_retry_failed",
                tool=retry_tool.tool,
                reason=retry_error,
            )
            return rows, tool_info  # fall back to first attempt results

        return retry_rows, retry_info

    async def _dispatch_tool(
        self,
        tool_call: ToolCall,
        neo4j_service: Any,
    ) -> tuple[list[dict[str, Any]], str, str | None]:
        """Execute a tool call against Neo4jService.

        Returns ``(rows, tool_info_json, error_or_none)``.
        """
        tool_info = json.dumps({"tool": tool_call.tool, "params": tool_call.params})
        try:
            rows = await asyncio.wait_for(
                self._dispatch_tool_inner(tool_call, neo4j_service),
                timeout=_EXECUTE_TIMEOUT_S,
            )
            return rows, tool_info, None
        except TimeoutError:
            logger.warning(
                "tool_dispatch_timeout",
                tool=tool_call.tool,
                timeout_s=_EXECUTE_TIMEOUT_S,
            )
            return [], tool_info, "Query timed out"
        except CypherValidationError as exc:
            return [], tool_info, f"Cypher rejected: {exc}"
        except Exception as exc:
            logger.warning(
                "tool_dispatch_error",
                tool=tool_call.tool,
                error=str(exc),
            )
            return [], tool_info, str(exc)

    async def _dispatch_tool_inner(
        self,
        tool_call: ToolCall,
        neo4j_service: Any,
    ) -> list[dict[str, Any]]:
        """Route to the correct Neo4jService method and normalise results."""
        p = tool_call.params

        match tool_call.tool:
            case "search":
                nodes = await neo4j_service.search(
                    query=p.get("query", ""),
                    labels=p.get("labels"),
                    limit=min(p.get("limit", 25), _MAX_LIMIT),
                )
                return _normalize_search(nodes)

            case "expand":
                node_ids = p.get("node_ids", [])
                if not node_ids:
                    return []
                nodes, edges = await neo4j_service.expand(
                    node_ids=node_ids,
                    rel_types=p.get("rel_types"),
                    hops=min(p.get("hops", 2), _MAX_HOPS),
                    limit=min(p.get("limit", 25), _MAX_LIMIT),
                )
                return _normalize_expand(nodes, edges)

            case "find_paths":
                source_id = p.get("source_id", "")
                target_id = p.get("target_id", "")
                if not source_id or not target_id:
                    return []
                paths, _nodes, _edges = await neo4j_service.find_paths(
                    source_id=source_id,
                    target_id=target_id,
                    max_hops=min(p.get("max_hops", 5), _MAX_HOPS),
                    mode=p.get("mode", "shortest"),
                )
                return _normalize_paths(paths)

            case "cypher":
                query_str = p.get("query", "")
                if not query_str:
                    return []
                clean = _SANITISER.sanitise(query_str)
                return await neo4j_service.execute_raw(clean)

            case _:
                return []

    async def _retry_tool_selection(
        self,
        original_tool: ToolCall,
        error_reason: str,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> ToolCall | None:
        """Ask the LLM to pick a different tool after failure."""
        system_prompt = GRAPH_TOOL_SELECTION_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            resolved_entities=resolved_entities or "(none)",
        )
        original_json = json.dumps(
            {"tool": original_tool.tool, "params": original_tool.params}
        )
        retry_msg = GRAPH_TOOL_RETRY_PROMPT.format(error_reason=error_reason)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent, query)},
            {"role": "assistant", "content": original_json},
            {"role": "user", "content": retry_msg},
        ]
        try:
            response = await self._client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.warning("tool_retry_llm_error", error=str(exc))
            return None

        content = _extract_content(response)
        return _parse_tool_call(content)

    # ------------------------------------------------------------------
    # Legacy Cypher generation (used by cypher tool retry path)
    # ------------------------------------------------------------------

    async def _generate_cypher(
        self,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> str:
        """Ask the LLM to produce a Cypher query (legacy, for cypher fallback)."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            resolved_entities=resolved_entities or "(none)",
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent, query)},
        ]
        try:
            response = await self._client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.warning("graph_retrieval_llm_error", error=str(exc))
            return ""

        content = _extract_content(response)
        return _clean_cypher_text(content)

    async def _sanitise_with_retry(
        self,
        cypher: str,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> str:
        """Sanitise the query; retry once if rejected."""
        first_reason = ""
        try:
            return _SANITISER.sanitise(cypher)
        except CypherValidationError as first_err:
            first_reason = str(first_err)
            logger.warning(
                "graph_retrieval_sanitiser_rejected",
                attempt=1,
                reason=first_reason,
            )

        # Retry: ask the LLM to fix the query
        retry_cypher = await self._retry_cypher(
            original_cypher=cypher,
            rejection_reason=first_reason,
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            query=query,
            resolved_entities=resolved_entities,
        )
        if not retry_cypher:
            return ""

        try:
            return _SANITISER.sanitise(retry_cypher)
        except CypherValidationError as second_err:
            logger.warning(
                "graph_retrieval_sanitiser_rejected",
                attempt=2,
                reason=str(second_err),
            )
            return ""

    async def _retry_cypher(
        self,
        original_cypher: str,
        rejection_reason: str,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        query: str = "",
        resolved_entities: str = "",
    ) -> str:
        """Ask the LLM to rewrite the rejected query."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            resolved_entities=resolved_entities or "(none)",
        )
        retry_user_msg = GRAPH_RETRIEVAL_RETRY_PROMPT.format(
            rejection_reason=rejection_reason,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent, query)},
            {"role": "assistant", "content": original_cypher},
            {"role": "user", "content": retry_user_msg},
        ]
        try:
            response = await self._client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.warning("graph_retrieval_retry_llm_error", error=str(exc))
            return ""

        content = _extract_content(response)
        return _clean_cypher_text(content)


# ---------------------------------------------------------------------------
# Normalizer functions
# ---------------------------------------------------------------------------


def _normalize_search(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten search results into row dicts for the synthesiser."""
    rows: list[dict[str, Any]] = []
    for node in nodes:
        row: dict[str, Any] = {
            "id": node.get("id", "?"),
            "labels": node.get("labels", []),
        }
        # Flatten properties into top-level keys
        for k, v in node.get("properties", {}).items():
            row[k] = v
        rows.append(row)
    return rows


def _normalize_expand(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Convert expand results into per-edge row dicts."""
    # Build node lookup for readable names
    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_map[node.get("id", "")] = node

    rows: list[dict[str, Any]] = []
    for edge in edges:
        source = node_map.get(edge.get("source", ""), {})
        target = node_map.get(edge.get("target", ""), {})
        rows.append(
            {
                "source_id": edge.get("source", ""),
                "source_name": _node_name(source),
                "source_labels": source.get("labels", []),
                "relationship": edge.get("type", "RELATED_TO"),
                "target_id": edge.get("target", ""),
                "target_name": _node_name(target),
                "target_labels": target.get("labels", []),
            }
        )
    return rows


def _normalize_paths(
    paths: list[list[Any]],
) -> list[dict[str, Any]]:
    """Convert find_paths results into path row dicts.

    Each path from Neo4jService.find_paths() is a flat list: all nodes first,
    then all edges.  We interleave them into the ``[node, edge, node, ...]``
    format expected by the synthesiser's ``_is_path()`` / ``_format_path()``.
    """
    rows: list[dict[str, Any]] = []
    for path_elements in paths:
        # Separate nodes (have "labels") from edges (have "type")
        nodes = [e for e in path_elements if "labels" in e]
        edges = [e for e in path_elements if "type" in e]

        if not nodes:
            continue

        # Reconstruct the interleaved path using edge source/target
        interleaved = _interleave_path(nodes, edges)
        rows.append({"p": interleaved})
    return rows


def _interleave_path(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Rebuild a ``[node, edge, node, edge, ...]`` sequence from nodes + edges.

    Uses edge source/target IDs to determine ordering.
    """
    if not edges:
        return nodes[:1] if nodes else []

    node_map = {n.get("id", ""): n for n in nodes}

    # Build adjacency from edges
    result: list[dict[str, Any]] = []
    used_edges: set[int] = set()

    # Find the start node: a node that appears as source but not as target
    # in the edge list, or just pick the first node
    source_ids = {e.get("source", "") for e in edges}
    target_ids = {e.get("target", "") for e in edges}
    start_candidates = source_ids - target_ids
    current_id = (
        next(iter(start_candidates)) if start_candidates else nodes[0].get("id", "")
    )

    for _ in range(len(edges) + 1):
        if current_id in node_map:
            result.append(node_map[current_id])
        else:
            break

        # Find the next edge from current_id
        found = False
        for i, edge in enumerate(edges):
            if i in used_edges:
                continue
            if edge.get("source", "") == current_id:
                result.append(edge)
                used_edges.add(i)
                current_id = edge.get("target", "")
                found = True
                break
            if edge.get("target", "") == current_id:
                result.append(edge)
                used_edges.add(i)
                current_id = edge.get("source", "")
                found = True
                break
        if not found:
            break

    return result


def _node_name(node: dict[str, Any]) -> str:
    """Extract a display name from a node dict."""
    props = node.get("properties", {})
    return str(
        props.get("name")
        or props.get("title")
        or props.get("_primary_value")
        or node.get("id", "?")
    )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_entity_names(text: str) -> list[str]:
    """Parse a JSON array of entity names from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        names = json.loads(text)
        if isinstance(names, list):
            return [str(n).strip() for n in names if n and str(n).strip()]
    except (json.JSONDecodeError, ValueError):
        logger.warning("entity_extraction_parse_error", text=text[:200])
    return []


def _parse_tool_call(text: str) -> ToolCall | None:
    """Parse a ToolCall from LLM output (JSON or raw Cypher fallback)."""
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()

    # Try JSON parse first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "tool" in data:
            return ToolCall(
                tool=data["tool"],
                params=data.get("params", {}),
            )
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: if LLM outputs raw Cypher (starts with MATCH/WITH/OPTIONAL)
    upper = text.upper().lstrip()
    if upper.startswith(("MATCH", "WITH", "OPTIONAL")):
        logger.debug("tool_selection_cypher_fallback", raw_text=text[:200])
        return ToolCall(tool="cypher", params={"query": text})

    logger.warning("tool_selection_parse_error", text=text[:200])
    return None


def _build_retrieval_query(intent: RouterIntent, query: str = "") -> str:
    """Build the user-turn message for tool selection."""
    parts = []
    if query:
        parts.append(f"User question: {query}")
    if intent.cypher_hint:
        parts.append(f"Cypher hint: {intent.cypher_hint}")
    return "\n".join(parts) if parts else "Generate a relevant Cypher query."


def _extract_content(response: Any) -> str:
    """Pull assistant message text from an OpenRouter response."""
    try:
        choices = response.get("choices", [])
        if not choices:
            return ""
        return choices[0]["message"]["content"] or ""
    except (KeyError, IndexError, AttributeError):
        return ""


def _clean_cypher_text(text: str) -> str:
    """Strip markdown fences and leading/trailing whitespace."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    return text


def _rows_to_evidence(rows: list[dict[str, Any]]) -> list[EvidenceSource]:
    """Convert raw row dicts to EvidenceSource objects (up to 20)."""
    evidence: list[EvidenceSource] = []
    for i, row in enumerate(rows[:20]):
        # Build a human-readable content string from the row values
        content = "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)
        evidence.append(
            EvidenceSource(
                type="graph_path",
                id=f"row_{i}",
                content=content[:500],  # cap per-evidence content length
            )
        )
    return evidence
