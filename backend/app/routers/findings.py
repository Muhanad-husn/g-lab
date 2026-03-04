"""Findings endpoints.

All endpoints are prefixed with /api/v1/sessions (set in main.py).
Findings are always scoped to a parent session.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_action_logger, get_db
from app.models.enums import ActionType
from app.models.schemas import FindingCreate, FindingUpdate
from app.services.action_log import ActionLogger
from app.services.finding_service import FindingService
from app.utils.response import envelope

router = APIRouter()
_svc = FindingService()


@router.get("/{session_id}/findings")
async def list_findings(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    findings = await _svc.list_for_session(db, session_id)
    return envelope([f.model_dump() for f in findings])


@router.post("/{session_id}/findings", status_code=201)
async def create_finding(
    session_id: str,
    body: FindingCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    finding = await _svc.create(db, session_id, body)
    background_tasks.add_task(
        action_logger.log,
        session_id=session_id,
        action_type=ActionType.FINDING_SAVE,
        actor="user",
        payload={"title": body.title, "has_snapshot": body.snapshot_png is not None},
    )
    return envelope(finding.model_dump())


@router.put("/{session_id}/findings/{finding_id}")
async def update_finding(
    session_id: str,
    finding_id: str,
    body: FindingUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    finding = await _svc.update(db, session_id, finding_id, body)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    background_tasks.add_task(
        action_logger.log,
        session_id=session_id,
        action_type=ActionType.FINDING_UPDATE,
        actor="user",
        payload={"finding_id": finding_id},
    )
    return envelope(finding.model_dump())


@router.delete("/{session_id}/findings/{finding_id}")
async def delete_finding(
    session_id: str,
    finding_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    deleted = await _svc.delete(db, session_id, finding_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Finding not found")
    background_tasks.add_task(
        action_logger.log,
        session_id=session_id,
        action_type=ActionType.FINDING_DELETE,
        actor="user",
        payload={"finding_id": finding_id},
    )
    return envelope({"deleted": finding_id})
