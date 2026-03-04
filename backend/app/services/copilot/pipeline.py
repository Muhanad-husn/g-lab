"""Copilot pipeline orchestrator.

Wires RouterService → GraphRetrievalService → SynthesiserService and
handles:
- Status events (routing, retrieving, re_retrieving)
- Re-retrieval when synthesiser confidence < 0.40
- 120-second global timeout
- Semaphore-based concurrency guard (max 1 concurrent copilot request)
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from app.core.logging import get_logger
from app.models.schemas import CopilotQueryRequest, PresetConfig, RouterIntent
from app.services.copilot.graph_retrieval import GraphRetrievalService
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.router import RouterService
from app.services.copilot.sse import SSEEvent
from app.services.copilot.synthesiser import SynthesiserService
from app.services.guardrails import GuardrailService

logger: Any = get_logger(__name__)

_COPILOT_TIMEOUT_S = 120.0
_RE_RETRIEVAL_THRESHOLD = 0.40  # confidence < this triggers re-retrieval

_GUARDRAILS = GuardrailService()


class CopilotPipeline:
    """Orchestrate the full copilot pipeline for a single query."""

    def execute(
        self,
        request: CopilotQueryRequest,
        neo4j_service: Any,
        openrouter_client: OpenRouterClient,
        preset_config: PresetConfig,
        session_id: str,
        semaphore: asyncio.Semaphore,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Return an async generator that runs the full pipeline.

        Callers: ``async for event in pipeline.execute(...)``.

        Emits (in order):
        - ``status`` events: ``routing``, ``retrieving``, optionally
          ``re_retrieving``
        - All events from :class:`SynthesiserService`
        - ``error`` event on timeout or concurrency conflict
        """
        return self._run(
            request=request,
            neo4j_service=neo4j_service,
            openrouter_client=openrouter_client,
            preset_config=preset_config,
            session_id=session_id,
            semaphore=semaphore,
        )

    # ------------------------------------------------------------------
    # Internal async generators
    # ------------------------------------------------------------------

    async def _run(
        self,
        request: CopilotQueryRequest,
        neo4j_service: Any,
        openrouter_client: OpenRouterClient,
        preset_config: PresetConfig,
        session_id: str,
        semaphore: asyncio.Semaphore,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Top-level generator: semaphore guard + timeout wrapper."""
        # Concurrency check (non-blocking)
        guard = _GUARDRAILS.check_copilot_available(semaphore)
        if not guard.allowed:
            logger.warning("copilot_semaphore_busy", session_id=session_id)
            yield SSEEvent(
                event="error",
                data={"code": "busy", "message": "Copilot is already processing a request"},
            )
            return

        await semaphore.acquire()
        logger.debug("copilot_semaphore_acquired", session_id=session_id)
        try:
            try:
                async with asyncio.timeout(_COPILOT_TIMEOUT_S):
                    async for event in self._execute_pipeline(
                        request=request,
                        neo4j_service=neo4j_service,
                        openrouter_client=openrouter_client,
                        preset_config=preset_config,
                    ):
                        yield event
            except TimeoutError:
                logger.warning(
                    "copilot_timeout",
                    session_id=session_id,
                    timeout_s=_COPILOT_TIMEOUT_S,
                )
                yield SSEEvent(
                    event="error",
                    data={"code": "timeout", "message": "Copilot request timed out"},
                )
        finally:
            semaphore.release()
            logger.debug("copilot_semaphore_released", session_id=session_id)

    async def _execute_pipeline(
        self,
        request: CopilotQueryRequest,
        neo4j_service: Any,
        openrouter_client: OpenRouterClient,
        preset_config: PresetConfig,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Core pipeline logic: route → retrieve → synthesise → maybe re-retrieve."""
        models = preset_config.models
        budgets = preset_config.tokenBudgets

        router_model = models.get("router", "anthropic/claude-3-haiku-20240307")
        retrieval_model = models.get("graphRetrieval", "anthropic/claude-3-haiku-20240307")
        synth_model = models.get("synthesiser", "anthropic/claude-3-haiku-20240307")

        router_tokens = budgets.get("router", 256)
        retrieval_tokens = budgets.get("graphRetrieval", 512)
        synth_tokens = budgets.get("synthesiser", 4096)

        router_svc = RouterService(openrouter_client)
        retrieval_svc = GraphRetrievalService(openrouter_client)
        synthesiser_svc = SynthesiserService(openrouter_client)

        # ── Step 1: Intent routing ──────────────────────────────────────
        yield SSEEvent(event="status", data={"status": "routing"})
        intent = await router_svc.classify(
            query=request.query,
            graph_context_summary="",
            model=router_model,
            temperature=0.0,
            max_tokens=router_tokens,
        )
        logger.debug(
            "copilot_routed",
            needs_graph=intent.needs_graph,
            needs_docs=intent.needs_docs,
        )

        # ── Step 2: Graph retrieval ─────────────────────────────────────
        yield SSEEvent(event="status", data={"status": "retrieving"})
        rows, _evidence = await retrieval_svc.retrieve(
            intent=intent,
            schema_summary="",
            neo4j_service=neo4j_service,
            model=retrieval_model,
            temperature=0.0,
            max_tokens=retrieval_tokens,
        )
        logger.debug("copilot_retrieved", row_count=len(rows))

        # ── Step 3: First synthesis pass (buffered to inspect confidence)
        first_pass: list[SSEEvent] = []
        confidence_score: float | None = None
        async for event in synthesiser_svc.synthesise(
            query=request.query,
            graph_results=rows,
            graph_context="",
            model=synth_model,
            max_tokens=synth_tokens,
        ):
            first_pass.append(event)
            if event.event == "confidence" and isinstance(event.data, dict):
                confidence_score = float(event.data.get("score", 1.0))

        # ── Step 4: Re-retrieval if confidence is low ───────────────────
        if confidence_score is not None and confidence_score < _RE_RETRIEVAL_THRESHOLD:
            logger.info(
                "copilot_re_retrieving",
                confidence=confidence_score,
                threshold=_RE_RETRIEVAL_THRESHOLD,
            )
            yield SSEEvent(event="status", data={"status": "re_retrieving"})

            # Broaden the search scope (hint at wider graph traversal)
            broad_intent = RouterIntent(
                needs_graph=intent.needs_graph,
                needs_docs=intent.needs_docs,
                cypher_hint=_broaden_hint(intent.cypher_hint),
                doc_query=intent.doc_query,
            )
            re_rows, _ = await retrieval_svc.retrieve(
                intent=broad_intent,
                schema_summary="",
                neo4j_service=neo4j_service,
                model=retrieval_model,
                temperature=0.3,  # more exploratory
                max_tokens=retrieval_tokens,
            )
            combined = (rows + re_rows)[:50]
            async for event in synthesiser_svc.synthesise(
                query=request.query,
                graph_results=combined,
                graph_context="",
                model=synth_model,
                max_tokens=synth_tokens,
            ):
                yield event
        else:
            # Confidence acceptable — stream first-pass events
            for event in first_pass:
                yield event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _broaden_hint(original_hint: str | None) -> str:
    """Expand the Cypher hint to suggest a wider traversal."""
    base = original_hint or "MATCH related nodes"
    return f"Expand scope — traverse one additional hop: {base}"
