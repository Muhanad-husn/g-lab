"""Session lifecycle endpoints.

All endpoints are prefixed with /api/v1/sessions (set in main.py).

IMPORTANT: GET /last-active is defined BEFORE GET /{session_id} to
prevent FastAPI from matching the literal string "last-active" as a
path parameter.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_action_logger, get_db
from app.models.enums import ActionType
from app.models.schemas import SessionCreate, SessionUpdate
from app.services.action_log import ActionLogger
from app.services.session_service import SessionService
from app.utils.response import envelope, error_response

router = APIRouter()
_svc = SessionService()


# ---------------------------------------------------------------------------
# POST /sessions — create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_session(
    body: SessionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    session = await _svc.create(db, body)
    background_tasks.add_task(
        action_logger.log,
        session_id=session.id,
        action_type=ActionType.SESSION_CREATE,
        actor="user",
        payload={"name": body.name},
    )
    return envelope(session.model_dump())


# ---------------------------------------------------------------------------
# GET /sessions/last-active — MUST be before /{session_id}
# ---------------------------------------------------------------------------


@router.get("/last-active")
async def get_last_active_session(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _svc.get_last_active(db)
    return envelope(session.model_dump() if session else None)


# ---------------------------------------------------------------------------
# POST /sessions/import — stub (Stage 7)
# ---------------------------------------------------------------------------


@router.post("/import", status_code=501)
async def import_session() -> dict[str, Any]:
    return error_response(
        code="NOT_IMPLEMENTED",
        message="Session import is not yet available (Stage 7).",
    )


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _svc.get(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return envelope(session.model_dump())


# ---------------------------------------------------------------------------
# PUT /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _svc.update(db, session_id, body)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return envelope(session.model_dump())


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete("/{session_id}", status_code=200)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    deleted = await _svc.delete(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return envelope({"deleted": session_id})


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/reset
# ---------------------------------------------------------------------------


@router.post("/{session_id}/reset")
async def reset_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    session = await _svc.reset(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    background_tasks.add_task(
        action_logger.log,
        session_id=session_id,
        action_type=ActionType.SESSION_RESET,
        actor="user",
    )
    return envelope(session.model_dump())


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/export — stub (Stage 7)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/export", status_code=501)
async def export_session(session_id: str) -> dict[str, Any]:
    return error_response(
        code="NOT_IMPLEMENTED",
        message="Session export is not yet available (Stage 7).",
    )


# ---------------------------------------------------------------------------
# GET /sessions — list all (convenience)
# ---------------------------------------------------------------------------


@router.get("")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sessions = await _svc.list_all(db)
    return envelope([s.model_dump() for s in sessions])
