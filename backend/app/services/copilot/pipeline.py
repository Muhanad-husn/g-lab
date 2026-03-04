"""Copilot pipeline orchestrator.

Wires RouterService → GraphRetrievalService → SynthesiserService into a
single streaming async generator.  Handles re-retrieval on low confidence
and enforces the 120-second overall timeout.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import CopilotQueryRequest, PresetConfig, RouterIntent
from app.services.copilot.graph_retrieval import GraphRetrievalService
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.router import RouterService
from app.services.copilot.sse import SSEEvent
from app.services.copilot.synthesiser import SynthesiserService

logger: Any = get_logger(__name__)

_PIPELINE_TIMEOUT_S = 120.0
_LOW_CONFIDENCE_THRESHOLD = 0.40


class CopilotPipeline:
    """Orchestrate the full copilot query pipeline."""

    def execute(
        self,
        request: CopilotQueryRequest,
        neo4j_service: Any,
        openrouter_client: OpenRouterClient,
        preset_config: PresetConfig,
        session_id: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the pipeline and return an async generator of SSE events.

        Events emitted in order:
        - ``status`` (stage: routing / retrieving / re_retrieving)
        - Synthesiser events (text_chunk, evidence, graph_delta, confidence, done)
        - ``error`` on timeout or fatal error

        Args:
            request: The copilot query request.
            neo4j_service: A ``Neo4jService`` instance (may be None/degraded).
            openrouter_client: OpenRouter client for LLM calls.
            preset_config: Resolved preset configuration.
            session_id: Session ID (used for logging).

        Returns:
            Async generator of :class:`SSEEvent` objects.
        """
        router = RouterService(openrouter_client)
        retrieval = GraphRetrievalService(openrouter_client)
        synthesiser = SynthesiserService(openrouter_client)
        return self._run(
            request=request,
            neo4j_service=neo4j_service,
            router=router,
            retrieval=retrieval,
            synthesiser=synthesiser,
            preset_config=preset_config,
            session_id=session_id,
        )

    async def _run(
        self,
        request: CopilotQueryRequest,
        neo4j_service: Any,
        router: RouterService,
        retrieval: GraphRetrievalService,
        synthesiser: SynthesiserService,
        preset_config: PresetConfig,
        session_id: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Internal async generator — yields SSE events."""
        try:
            async with asyncio.timeout(_PIPELINE_TIMEOUT_S):
                schema_summary = await _build_schema_summary(neo4j_service)
                models = preset_config.models
                budgets = preset_config.tokenBudgets

                # --- Step 1: Route ---
                yield SSEEvent(event="status", data={"stage": "routing"})
                intent = await router.classify(
                    query=request.query,
                    graph_context_summary=schema_summary,
                    model=models.get("router", "anthropic/claude-3-haiku"),
                    temperature=0.0,
                    max_tokens=budgets.get("router", 256),
                )
                logger.debug(
                    "pipeline_routed",
                    session_id=session_id,
                    needs_graph=intent.needs_graph,
                )

                # --- Step 2: Retrieve ---
                yield SSEEvent(event="status", data={"stage": "retrieving"})
                rows, _evidence = await retrieval.retrieve(
                    intent=intent,
                    schema_summary=schema_summary,
                    neo4j_service=neo4j_service,
                    model=models.get("graphRetrieval", "anthropic/claude-3-haiku"),
                    temperature=0.0,
                    max_tokens=budgets.get("graphRetrieval", 512),
                )

                # --- Step 3: Synthesise (stream events to caller) ---
                first_confidence: float | None = None
                async for event in synthesiser.synthesise(
                    query=request.query,
                    graph_results=rows,
                    graph_context=schema_summary,
                    model=models.get("synthesiser", "anthropic/claude-3-haiku"),
                    temperature=0.7,
                    max_tokens=budgets.get("synthesiser", 4096),
                ):
                    yield event
                    if event.event == "confidence":
                        data = event.data if isinstance(event.data, dict) else {}
                        first_confidence = float(data.get("score", 1.0))

                # --- Step 4: Re-retrieve on low confidence ---
                if (
                    first_confidence is not None
                    and first_confidence < _LOW_CONFIDENCE_THRESHOLD
                ):
                    logger.debug(
                        "pipeline_low_confidence_re_retrieving",
                        session_id=session_id,
                        confidence=first_confidence,
                    )
                    yield SSEEvent(event="status", data={"stage": "re_retrieving"})
                    hops = preset_config.hops + 1
                    hint = f"Use {hops} hops. {intent.cypher_hint or ''}".strip()
                    re_intent = RouterIntent(
                        needs_graph=True,
                        needs_docs=intent.needs_docs,
                        cypher_hint=hint,
                        doc_query=intent.doc_query,
                    )
                    rows2, _evidence2 = await retrieval.retrieve(
                        intent=re_intent,
                        schema_summary=schema_summary,
                        neo4j_service=neo4j_service,
                        model=models.get("graphRetrieval", "anthropic/claude-3-haiku"),
                        temperature=0.0,
                        max_tokens=budgets.get("graphRetrieval", 512),
                    )
                    async for event in synthesiser.synthesise(
                        query=request.query,
                        graph_results=rows2,
                        graph_context=schema_summary,
                        model=models.get("synthesiser", "anthropic/claude-3-haiku"),
                        temperature=0.7,
                        max_tokens=budgets.get("synthesiser", 4096),
                    ):
                        yield event

        except TimeoutError:
            logger.warning(
                "copilot_pipeline_timeout",
                session_id=session_id,
                timeout_s=_PIPELINE_TIMEOUT_S,
            )
            yield SSEEvent(
                event="error",
                data={"message": "Pipeline timed out after 120 seconds"},
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


async def _build_schema_summary(neo4j_service: Any) -> str:
    """Build a brief schema summary string from Neo4j schema.

    Returns an empty string if neo4j_service is None or schema fetch fails.
    """
    if neo4j_service is None:
        return ""
    try:
        schema_data: dict[str, Any] = await neo4j_service.get_schema()
        labels = [lbl["name"] for lbl in schema_data.get("labels", [])[:10]]
        rels = [rt["name"] for rt in schema_data.get("relationship_types", [])[:10]]
        parts: list[str] = []
        if labels:
            parts.append(f"Node labels: {', '.join(labels)}")
        if rels:
            parts.append(f"Relationship types: {', '.join(rels)}")
        return ". ".join(parts)
    except Exception:
        return ""
