"""Copilot graph retrieval service.

Generates a read-only Cypher query from a RouterIntent, sanitises it,
executes it via Neo4jService, and maps results to EvidenceSource objects.

Retries once if the first generated query is rejected by the sanitiser.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import EvidenceSource, RouterIntent
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.prompts import (
    GRAPH_RETRIEVAL_RETRY_PROMPT,
    GRAPH_RETRIEVAL_SYSTEM_PROMPT,
)
from app.utils.cypher import CypherSanitiser
from app.utils.exceptions import CypherValidationError

logger: Any = get_logger(__name__)

_SANITISER = CypherSanitiser()
_EXECUTE_TIMEOUT_S = 30.0


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
    ) -> tuple[list[dict[str, Any]], list[EvidenceSource]]:
        """Generate a Cypher query and return raw rows + evidence sources.

        Args:
            intent: The classified intent from RouterService.
            schema_summary: Short description of the graph schema.
            neo4j_service: A ``Neo4jService`` instance for query execution.
            model: OpenRouter model ID for Cypher generation.
            temperature: Sampling temperature.
            max_tokens: Token budget for Cypher generation.

        Returns:
            A tuple ``(rows, evidence)`` where *rows* is the raw list of
            result dicts and *evidence* is a list of :class:`EvidenceSource`
            objects.  Returns ``([], [])`` on double sanitiser rejection or
            execution timeout.
        """
        if not intent.needs_graph:
            logger.debug("graph_retrieval_skipped", reason="needs_graph=False")
            return [], []

        # --- Step 1: generate Cypher ---
        cypher = await self._generate_cypher(
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not cypher:
            return [], []

        # --- Step 2: sanitise (retry once on rejection) ---
        clean_cypher = await self._sanitise_with_retry(
            cypher=cypher,
            intent=intent,
            schema_summary=schema_summary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not clean_cypher:
            return [], []

        # --- Step 3: execute ---
        rows = await self._execute(clean_cypher, neo4j_service)

        # --- Step 4: map to evidence sources ---
        evidence = _rows_to_evidence(rows)

        logger.debug(
            "graph_retrieval_complete",
            row_count=len(rows),
            evidence_count=len(evidence),
        )
        return rows, evidence

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_cypher(
        self,
        intent: RouterIntent,
        schema_summary: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Ask the LLM to produce a Cypher query."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent)},
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
    ) -> str:
        """Ask the LLM to rewrite the rejected query."""
        system_prompt = GRAPH_RETRIEVAL_SYSTEM_PROMPT.format(
            schema_summary=schema_summary or "(schema not available)",
            cypher_hint=intent.cypher_hint or "none",
        )
        retry_user_msg = GRAPH_RETRIEVAL_RETRY_PROMPT.format(
            rejection_reason=rejection_reason,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_retrieval_query(intent)},
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


def _build_retrieval_query(intent: RouterIntent) -> str:
    """Build the user-turn message for Cypher generation."""
    parts = []
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
