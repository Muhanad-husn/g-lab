"""Session lifecycle endpoints.

All endpoints are prefixed with /api/v1/sessions (set in main.py).

IMPORTANT: GET /last-active is defined BEFORE GET /{session_id} to
prevent FastAPI from matching the literal string "last-active" as a
path parameter.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.logging import get_logger
from app.dependencies import get_action_logger, get_db, get_settings
from app.models.db import Finding as FindingModel
from app.models.enums import ActionType
from app.models.schemas import (
    CanvasState,
    FindingCreate,
    SessionCreate,
    SessionUpdate,
)
from app.services.action_log import ActionLogger
from app.services.finding_service import FindingService
from app.services.session_service import SessionService
from app.utils.export import (
    pack_session,
    read_ndjson_if_exists,
    unpack_session,
    validate_manifest,
    write_ndjson,
)
from app.utils.response import envelope

router = APIRouter()
_svc = SessionService()
_finding_svc = FindingService()
_logger: Any = get_logger(__name__)


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
# POST /sessions/import
# ---------------------------------------------------------------------------


@router.post("/import", status_code=201)
async def import_session(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    zip_bytes = await file.read()

    try:
        archive = unpack_session(zip_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        warnings = validate_manifest(archive["manifest"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_meta: dict[str, Any] = archive["session"]
    canvas_raw: dict[str, Any] = archive["canvas"]
    findings_raw: list[dict[str, Any]] = archive["findings"]
    snapshots: dict[str, bytes] = archive["snapshots"]
    action_log_ndjson: str = archive["action_log_ndjson"]

    # Create a new session with a new UUID (never reuse the archived ID)
    new_session = await _svc.create(
        db, SessionCreate(name=session_meta.get("name", "Imported Session"))
    )

    # Apply canvas state + config from archive
    canvas_state = CanvasState.model_validate(canvas_raw)
    raw_config = session_meta.get("config", {})
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    updated = await _svc.update(
        db,
        new_session.id,
        SessionUpdate(canvas_state=canvas_state, config=config),
    )
    if updated is not None:
        new_session = updated

    # Write action log to new session's data dir path (best-effort)
    if action_log_ndjson:
        ndjson_path = (
            settings.GLAB_DATA_DIR / "sessions" / new_session.id / "action_log.ndjson"
        )
        try:
            await asyncio.to_thread(write_ndjson, ndjson_path, action_log_ndjson)
        except Exception as exc:
            _logger.warning("import.ndjson_write_failed", error=str(exc))

    # Recreate findings (new UUIDs; snapshot bytes re-encoded to base64 for the service)
    for fd in findings_raw:
        old_id: str = fd.get("id", "")
        snapshot_b64: str | None = None
        if old_id in snapshots:
            snapshot_b64 = base64.b64encode(snapshots[old_id]).decode()
        await _finding_svc.create(
            db,
            new_session.id,
            FindingCreate(
                title=fd.get("title", ""),
                body=fd.get("body"),
                snapshot_png=snapshot_b64,
                canvas_context=fd.get("canvas_context"),
            ),
        )

    background_tasks.add_task(
        action_logger.log,
        session_id=new_session.id,
        action_type=ActionType.SESSION_IMPORT,
        actor="user",
        payload={
            "original_session_id": session_meta.get("id"),
            "finding_count": len(findings_raw),
        },
    )

    return envelope(new_session.model_dump(), warnings=warnings)


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
# POST /sessions/{session_id}/export
# ---------------------------------------------------------------------------


@router.post("/{session_id}/export")
async def export_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    session = await _svc.get(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Split canvas_state out of session dict (goes to canvas.json separately)
    session_dict = session.model_dump()
    canvas_data: dict[str, Any] = session_dict.pop("canvas_state", {})

    # Query raw Finding rows (need snapshot_png bytes, not in FindingResponse)
    result = await db.execute(
        select(FindingModel).where(FindingModel.session_id == session_id)
    )
    finding_rows = result.scalars().all()

    findings_data: list[dict[str, Any]] = []
    snapshots: dict[str, bytes] = {}
    for row in finding_rows:
        findings_data.append(
            {
                "id": row.id,
                "session_id": row.session_id,
                "title": row.title,
                "body": row.body,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "has_snapshot": row.snapshot_png is not None,
                "canvas_context": (
                    json.loads(row.canvas_context) if row.canvas_context else None
                ),
            }
        )
        if row.snapshot_png:
            snapshots[row.id] = row.snapshot_png

    # Read NDJSON from disk (source of truth); empty string if not yet written
    ndjson_path = settings.GLAB_DATA_DIR / "sessions" / session_id / "action_log.ndjson"
    try:
        action_log_ndjson = await asyncio.to_thread(read_ndjson_if_exists, ndjson_path)
    except Exception:
        action_log_ndjson = ""

    zip_bytes = pack_session(
        session_data=session_dict,
        canvas_data=canvas_data,
        findings_data=findings_data,
        action_log_ndjson=action_log_ndjson,
        snapshots=snapshots,
    )

    background_tasks.add_task(
        action_logger.log,
        session_id=session_id,
        action_type=ActionType.SESSION_EXPORT,
        actor="user",
        payload={"finding_count": len(findings_data)},
    )

    filename = f"{session_id}.g-lab-session"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
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
