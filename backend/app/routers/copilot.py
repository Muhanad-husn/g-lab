"""Copilot endpoints.

All endpoints are prefixed with /api/v1/copilot (set in main.py).

Routes:
  POST /copilot/query              — stream copilot response (SSE)
  GET  /copilot/history/{session_id} — list conversation messages
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.dependencies import (
    get_action_logger,
    get_copilot_semaphore,
    get_db,
    get_openrouter,
)
from app.models.enums import ActionType
from app.models.schemas import CopilotQueryRequest, PresetConfig
from app.services.action_log import ActionLogger
from app.services.conversation_service import ConversationService
from app.services.copilot.openrouter import OpenRouterClient
from app.services.copilot.pipeline import CopilotPipeline, format_schema_summary
from app.services.copilot.sse import format_sse
from app.services.guardrails import GuardrailService
from app.utils.response import envelope, error_response

router = APIRouter()
_svc = ConversationService()
_pipeline = CopilotPipeline()
_guardrails = GuardrailService()
_logger: Any = get_logger(__name__)


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------


@router.post("/query")
async def query(
    body: CopilotQueryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    openrouter: OpenRouterClient | None = Depends(get_openrouter),
    semaphore: asyncio.Semaphore = Depends(get_copilot_semaphore),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> Any:
    """Stream a copilot response as Server-Sent Events.

    Returns 503 if OpenRouter is not configured.
    Returns 409 if another copilot request is already in flight.
    """
    if openrouter is None:
        raise HTTPException(
            status_code=503,
            detail="OpenRouter is not configured (OPENROUTER_API_KEY not set)",
        )

    # Pre-flight: 409 if semaphore is already locked
    guard = _guardrails.check_copilot_available(semaphore)
    if not guard.allowed:
        return JSONResponse(
            status_code=409,
            content=error_response(
                code="copilot_busy",
                message="Copilot is already processing a request",
                detail=guard.detail,
            ),
        )

    # Get optional Neo4j service (degraded mode — may be None)
    neo4j_svc: Any = getattr(request.app.state, "neo4j_service", None)

    # Fetch Neo4j schema for LLM context (labels, rel types, properties)
    schema_summary = ""
    if neo4j_svc is not None:
        try:
            schema = await neo4j_svc.get_schema()
            schema_summary = format_schema_summary(schema)
        except Exception as exc:
            _logger.warning("copilot_schema_fetch_failed", error=str(exc))

    # Resolve preset config, applying frontend model overrides if provided
    preset_config = PresetConfig()
    if body.model_assignments:
        preset_config = preset_config.model_copy(
            update={"models": {**preset_config.models, **body.model_assignments}}
        )

    # Get session factory for post-stream DB writes
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.db_session_factory
    )

    async def _event_stream() -> AsyncGenerator[str, None]:
        full_text: list[str] = []
        async for event in _pipeline.execute(
            request=body,
            neo4j_service=neo4j_svc,
            openrouter_client=openrouter,
            preset_config=preset_config,
            session_id=body.session_id,
            semaphore=semaphore,
            schema_summary=schema_summary,
            canvas_summary=body.canvas_summary or "",
        ):
            # Collect assistant text for conversation storage
            if event.event == "text_chunk" and isinstance(event.data, dict):
                chunk = event.data.get("text", "")
                if chunk:
                    full_text.append(chunk)
            yield format_sse(event)

        # After stream completes — store conversation messages
        assistant_text = "".join(full_text)
        if assistant_text:
            async with session_factory() as conv_db:
                await _svc.save_message(conv_db, body.session_id, "user", body.query)
                await _svc.save_message(
                    conv_db,
                    body.session_id,
                    "assistant",
                    assistant_text,
                )
            _logger.debug(
                "conversation_stored",
                session_id=body.session_id,
                text_len=len(assistant_text),
            )

    # Log action (fire-and-forget)
    background_tasks.add_task(
        action_logger.log,
        session_id=body.session_id,
        action_type=ActionType.COPILOT_QUERY,
        actor="copilot",
        payload={
            "query": body.query,
            "include_graph_context": body.include_graph_context,
        },
        result_summary=None,
        guardrail_warnings=None,
    )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /history/{session_id}
# ---------------------------------------------------------------------------


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return conversation history for a session (oldest first, max *limit*)."""
    messages = await _svc.get_history(db, session_id, limit=limit)
    return envelope([m.model_dump() for m in messages])
