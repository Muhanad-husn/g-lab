"""Copilot router service — intent classification.

Classifies a user query into a RouterIntent that tells the pipeline
whether graph retrieval, document retrieval, or both are needed.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import RouterIntent
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.prompts import ROUTER_SYSTEM_PROMPT

logger: Any = get_logger(__name__)

# Fallback when LLM response cannot be parsed
_FALLBACK_INTENT = RouterIntent(needs_graph=True, needs_docs=False)


class RouterService:
    """Classify a user query into a RouterIntent."""

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    async def classify(
        self,
        query: str,
        graph_context_summary: str = "",
        model: str = "anthropic/claude-3-haiku",
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> RouterIntent:
        """Classify *query* and return a RouterIntent.

        Args:
            query: The raw user question.
            graph_context_summary: Short description of the current graph
                schema (labels, relationship types, node counts).  May be
                empty when Neo4j is degraded.
            model: OpenRouter model ID to use for classification.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Token budget for the classification response.

        Returns:
            A :class:`RouterIntent` — falls back to ``needs_graph=True``
            on any parse failure.
        """
        if not query.strip():
            logger.debug("router_empty_query")
            return _FALLBACK_INTENT

        system_prompt = ROUTER_SYSTEM_PROMPT.format(
            schema_summary=graph_context_summary or "(schema not available)"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
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
            logger.warning("router_llm_error", error=str(exc))
            return _FALLBACK_INTENT

        content = _extract_content(response)
        if not content:
            logger.warning("router_empty_response")
            return _FALLBACK_INTENT

        intent = _parse_intent(content)
        logger.debug(
            "router_classified",
            needs_graph=intent.needs_graph,
            needs_docs=intent.needs_docs,
        )
        return intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_content(response: Any) -> str:
    """Pull the assistant message text out of an OpenRouter response dict."""
    try:
        choices = response.get("choices", [])
        if not choices:
            return ""
        return choices[0]["message"]["content"] or ""
    except (KeyError, IndexError, AttributeError):
        return ""


def _parse_intent(text: str) -> RouterIntent:
    """Parse the LLM JSON output into a RouterIntent.

    Falls back to the default intent on any error.
    """
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()

    try:
        data = json.loads(text)
        return RouterIntent(
            needs_graph=bool(data.get("needs_graph", True)),
            needs_docs=bool(data.get("needs_docs", False)),
            cypher_hint=data.get("cypher_hint") or None,
            doc_query=data.get("doc_query") or None,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("router_parse_failure", error=str(exc))
        return _FALLBACK_INTENT
