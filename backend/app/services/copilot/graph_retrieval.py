"""Copilot graph retrieval service.

Resolves entity names from the user query against the actual graph database,
then generates a Cypher query using the resolved entities, sanitises it,
executes it, and maps results to EvidenceSource objects.

Flow: extract entities → search Neo4j → generate Cypher → sanitise → execute.
Retries once if the generated query is rejected by the sanitiser.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import EvidenceSource, RouterIntent
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.prompts import (
    ENTITY_EXTRACTION_PROMPT,
    GRAPH_RETRIEVAL_RETRY_PROMPT,
    GRAPH_RETRIEVAL_SYSTEM_PROMPT,
)
from app.utils.cypher import CypherSanitiser
from app.utils.exceptions import CypherValidationError

logger: Any = get_logger(__name__)

_SANITISER = CypherSanitiser()
_EXECUTE_TIMEOUT_S = 30.0
_ENTITY_SEARCH_LIMIT = 3  # max results per entity name


class GraphRetrievalService:
    """Generate and execute a Cypher query from an intent + schema summary."""

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    async def retrieve(
        self,
        intent: RouterIntent,
        schema_summary: str,
        neo4j_service: Any,
        model: str = "anthropic/claude-3-haiku",
        temperature: float = 0.0,
        max_tokens: int = 512,
        canvas_summary: str = "",
        query: str = "",
    ) -> tuple[list[dict[str, Any]], list[EvidenceSource]]:
        """Generate a Cypher query and return raw rows + evidence sources.

        Flow:
        1. Extract entity names from the user query (LLM call).
        2. Resolve each entity against Neo4j via text search.
        3. Generate a Cypher query using resolved entity context.
        4. Sanitise (retry once on rejection).
        5. Execute and map results to evidence.

        Returns ``([], [])`` on skip, double rejection, or timeout.
        """
        if not intent.needs_graph:
            logger.debug("graph_retrieval_skipped", reason="needs_graph=False")
            return [], []

        # --- Step 1: resolve entities from the query ---
        resolved = await self._resolve_entities(
            query=query,
            neo4j_service=neo4j_service,
            model=model,
        )

        # --- Step 2: generate Cypher with resolved entity context ---
        cypher = await self._generate_cypher(
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            canvas_summary=canvas_summary,
            query=query,
            resolved_entities=resolved,
        )
        if not cypher:
            return [], []

        # --- Step 3: sanitise (retry once on rejection) ---
        clean_cypher = await self._sanitise_with_retry(
            cypher=cypher,
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            canvas_summary=canvas_summary,
            query=query,
            resolved_entities=resolved,
        )
        if not clean_cypher:
            return [], []

        # --- Step 4: execute ---
        rows = await self._execute(clean_cypher, neo4j_service)

        # --- Step 5: map to evidence sources ---
        evidence = _rows_to_evidence(rows)

        logger.debug(
            "graph_retrieval_complete",
            row_count=len(rows),
            evidence_count=len(evidence),
        )
        return rows, evidence

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

        Returns a formatted string of resolved entities for the Cypher prompt.
        """
        if not query:
            return "(no entities)"

        # Ask LLM to extract entity names
        names = await self._extract_entity_names(query, model)
        if not names:
            return "(no entities detected)"

        logger.debug("entity_extraction", names=names)

        # Search Neo4j for each entity name in parallel
        search_tasks = [
            self._search_entity(name, neo4j_service) for name in names
        ]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Format results
        lines: list[str] = []
        for name, result in zip(names, results):
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
                prop_str = ", ".join(
                    f"{k}={v!r}" for k, v in list(props.items())[:5]
                )
                lines.append(
                    f'"{name}" → elementId={node_id!r}, '
                    f"labels={labels}, {prop_str}"
                )
        return "\n".join(lines) if lines else "(no entities resolved)"

    async def _extract_entity_names(
        self, query: str, model: str
    ) -> list[str]:
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
            logger.warning(
                "entity_search_error", name=name, error=str(exc)
            )
            return []

    # ------------------------------------------------------------------
    # Cypher generation
    # ------------------------------------------------------------------

    async def _generate_cypher(
        self,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
        canvas_summary: str = "",
        query: str = "",
        resolved_entities: str = "",
    ) -> str:
        """Ask the LLM to produce a Cypher query."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            canvas_context=canvas_summary or "(empty canvas)",
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
        canvas_summary: str = "",
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
            canvas_summary=canvas_summary,
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
        canvas_summary: str = "",
        query: str = "",
        resolved_entities: str = "",
    ) -> str:
        """Ask the LLM to rewrite the rejected query."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
            canvas_context=canvas_summary or "(empty canvas)",
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

    async def _execute(
        self,
        cypher: str,
        neo4j_service: Any,
    ) -> list[dict[str, Any]]:
        """Execute *cypher* with a 30-second timeout."""
        try:
            rows: list[dict[str, Any]] = await asyncio.wait_for(
                neo4j_service.execute_raw(cypher),
                timeout=_EXECUTE_TIMEOUT_S,
            )
            return rows
        except TimeoutError:
            logger.warning("graph_retrieval_timeout", timeout_s=_EXECUTE_TIMEOUT_S)
            return []
        except Exception as exc:
            logger.warning("graph_retrieval_execute_error", error=str(exc))
            return []


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


def _build_retrieval_query(intent: RouterIntent, query: str = "") -> str:
    """Build the user-turn message for Cypher generation."""
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
