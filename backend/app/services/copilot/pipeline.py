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
import json
from collections.abc import AsyncGenerator
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import (
    CopilotQueryRequest,
    DocumentChunk,
    PresetConfig,
    RouterIntent,
)
from app.services.copilot.document_retrieval import DocumentRetrievalRole
from app.services.copilot.graph_retrieval import GraphRetrievalService
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.router import RouterService
from app.services.copilot.sse import SSEEvent
from app.services.copilot.synthesiser import SynthesiserService
from app.services.guardrails import GuardrailService

logger: Any = get_logger(__name__)

_COPILOT_TIMEOUT_S = 300.0
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
        retrieval_service: Any = None,
        reranker_service: Any = None,
        library_id: str | None = None,
        schema_summary: str = "",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Return an async generator that runs the full pipeline.

        Callers: ``async for event in pipeline.execute(...)``.

        Emits (in order):
        - ``status`` events: ``routing``, ``retrieving``, optionally
          ``re_retrieving``
        - All events from :class:`SynthesiserService`
        - ``error`` event on timeout or concurrency conflict

        Args:
            retrieval_service: Optional :class:`DocumentRetrievalService`.
                When provided alongside ``reranker_service`` and
                ``library_id``, document retrieval runs in parallel with
                graph retrieval when ``intent.needs_docs=True``.
            reranker_service: Optional :class:`RerankerService`.
            library_id: ID of the session-attached document library, if any.
            conversation_history: Prior user/assistant messages for multi-turn.
        """
        return self._run(
            request=request,
            neo4j_service=neo4j_service,
            openrouter_client=openrouter_client,
            preset_config=preset_config,
            session_id=session_id,
            semaphore=semaphore,
            retrieval_service=retrieval_service,
            reranker_service=reranker_service,
            library_id=library_id,
            schema_summary=schema_summary,
            conversation_history=conversation_history,
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
        retrieval_service: Any = None,
        reranker_service: Any = None,
        library_id: str | None = None,
        schema_summary: str = "",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Top-level generator: semaphore guard + timeout wrapper."""
        # Concurrency check (non-blocking)
        guard = _GUARDRAILS.check_copilot_available(semaphore)
        if not guard.allowed:
            logger.warning("copilot_semaphore_busy", session_id=session_id)
            yield SSEEvent(
                event="error",
                data={
                    "code": "busy",
                    "message": "Copilot is already processing a request",
                },
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
                        retrieval_service=retrieval_service,
                        reranker_service=reranker_service,
                        library_id=library_id,
                        schema_summary=schema_summary,
                        conversation_history=conversation_history,
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
        retrieval_service: Any = None,
        reranker_service: Any = None,
        library_id: str | None = None,
        schema_summary: str = "",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Core pipeline logic: route → retrieve → synthesise → maybe re-retrieve."""
        models = preset_config.models
        budgets = preset_config.tokenBudgets

        router_model = models.get("router", "anthropic/claude-3-haiku")
        retrieval_model = models.get(
            "graphRetrieval", "anthropic/claude-3-haiku"
        )
        synth_model = models.get("synthesiser", "anthropic/claude-3-haiku")

        router_tokens = budgets.get("router", 256)
        retrieval_tokens = budgets.get("graphRetrieval", 512)
        synth_tokens = budgets.get("synthesiser", 4096)
        context_window_tokens = budgets.get("contextWindow", 128_000)

        doc_top_k = _GUARDRAILS.SOFT_LIMITS["doc_retrieval_top_k"]
        reranker_top_k = _GUARDRAILS.SOFT_LIMITS["reranker_top_k"]

        router_svc = RouterService(openrouter_client)
        graph_retrieval_svc = GraphRetrievalService(openrouter_client)
        synthesiser_svc = SynthesiserService(openrouter_client)

        # ── Step 1: Intent routing ──────────────────────────────────────
        yield SSEEvent(event="status", data={"stage": "routing"})
        intent = await router_svc.classify(
            query=request.query,
            graph_context_summary=schema_summary,
            model=router_model,
            temperature=0.0,
            max_tokens=router_tokens,
        )
        logger.debug(
            "copilot_routed",
            needs_graph=intent.needs_graph,
            needs_docs=intent.needs_docs,
        )

        # ── Step 2: Parallel graph + document retrieval ─────────────────
        yield SSEEvent(event="status", data={"stage": "retrieving"})

        doc_role: DocumentRetrievalRole | None = None
        if retrieval_service is not None and reranker_service is not None:
            doc_role = DocumentRetrievalRole(retrieval_service, reranker_service)

        if doc_role is not None and library_id:
            yield SSEEvent(event="status", data={"stage": "retrieving_docs"})

        graph_coro = graph_retrieval_svc.retrieve(
            intent=intent,
            schema_summary=schema_summary,
            neo4j_service=neo4j_service,
            model=retrieval_model,
            temperature=0.0,
            max_tokens=retrieval_tokens,
            query=request.query,
        )
        doc_coro = (
            doc_role.retrieve(
                intent=intent,
                library_id=library_id,
                top_k=doc_top_k,
                reranker_top_k=reranker_top_k,
                user_query=request.query,
            )
            if doc_role is not None
            else _empty_doc_result()
        )

        (
            (rows, _graph_evidence, cypher_used),
            (doc_chunks, doc_evidence),
        ) = await asyncio.gather(graph_coro, doc_coro)
        logger.debug(
            "copilot_retrieved",
            row_count=len(rows),
            doc_chunk_count=len(doc_chunks),
        )

        if cypher_used:
            try:
                tool_info = json.loads(cypher_used)
                yield SSEEvent(event="tool_used", data=tool_info)
            except (json.JSONDecodeError, ValueError):
                yield SSEEvent(
                    event="tool_used",
                    data={"cypher": cypher_used},
                )

        if doc_evidence:
            yield SSEEvent(
                event="doc_evidence",
                data={"sources": [e.model_dump() for e in doc_evidence]},
            )

        # ── Step 3: First synthesis pass (buffered to inspect confidence)
        first_pass: list[SSEEvent] = []
        confidence_score: float | None = None
        async for event in synthesiser_svc.synthesise(
            query=request.query,
            graph_results=rows,
            graph_context=schema_summary,
            model=synth_model,
            max_tokens=synth_tokens,
            doc_chunks=doc_chunks,
            conversation_history=conversation_history,
            context_window_tokens=context_window_tokens,
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
            yield SSEEvent(event="status", data={"stage": "re_retrieving"})

            # Broaden the graph search scope
            broad_intent = RouterIntent(
                needs_graph=intent.needs_graph,
                needs_docs=intent.needs_docs,
                cypher_hint=_broaden_hint(intent.cypher_hint),
                doc_query=intent.doc_query,
            )
            re_graph_coro = graph_retrieval_svc.retrieve(
                intent=broad_intent,
                schema_summary=schema_summary,
                neo4j_service=neo4j_service,
                model=retrieval_model,
                temperature=0.3,  # more exploratory
                max_tokens=retrieval_tokens,
                query=request.query,
            )
            # Increase doc top-k by 5 on re-retrieval
            re_doc_coro = (
                doc_role.retrieve(
                    intent=broad_intent,
                    library_id=library_id,
                    top_k=doc_top_k + 5,
                    reranker_top_k=reranker_top_k,
                    user_query=request.query,
                )
                if doc_role is not None
                else _empty_doc_result()
            )
            (re_rows, _, _re_cypher), (re_doc_chunks, _) = await asyncio.gather(
                re_graph_coro, re_doc_coro
            )
            combined_rows = (rows + re_rows)[:50]
            combined_docs = (doc_chunks + re_doc_chunks)[: reranker_top_k * 2]
            async for event in synthesiser_svc.synthesise(
                query=request.query,
                graph_results=combined_rows,
                graph_context=schema_summary,
                model=synth_model,
                max_tokens=synth_tokens,
                doc_chunks=combined_docs,
                conversation_history=conversation_history,
                context_window_tokens=context_window_tokens,
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


async def _empty_doc_result() -> tuple[list[DocumentChunk], list[Any]]:
    """Coroutine that returns empty doc retrieval results (no library/service)."""
    return [], []


def format_schema_summary(schema: dict[str, Any]) -> str:
    """Format a Neo4j schema dict into a concise LLM-readable summary.

    Expects the shape returned by ``Neo4jService.get_schema()``:
    ``{"labels": [...], "relationship_types": [...]}``.
    """
    parts: list[str] = []

    labels = schema.get("labels") or []
    if labels:
        parts.append("Node labels:")
        for info in labels:
            label = info.get("name") or info.get("label", "?")
            count = info.get("count")
            props = info.get("property_keys") or []
            count_str = f" ({count} nodes)" if count is not None else ""
            props_str = f" — properties: {', '.join(props)}" if props else ""
            parts.append(f"  :{label}{count_str}{props_str}")

    rel_types = schema.get("relationship_types") or []
    if rel_types:
        parts.append("Relationship types:")
        for info in rel_types:
            rel_type = info.get("name") or info.get("type", "?")
            count = info.get("count")
            props = info.get("property_keys") or []
            count_str = f" ({count} rels)" if count is not None else ""
            props_str = f" — properties: {', '.join(props)}" if props else ""
            parts.append(f"  [:{rel_type}]{count_str}{props_str}")

    return "\n".join(parts) if parts else ""
