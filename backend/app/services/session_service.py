"""Session lifecycle service.

All DB access uses the injected AsyncSession. Callers do NOT commit —
this service layer owns transaction boundaries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Session as SessionModel
from app.models.schemas import (
    CanvasState,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)

# Canonical empty canvas JSON (matches db.py default)
_EMPTY_CANVAS = CanvasState().model_dump()


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_response(row: SessionModel) -> SessionResponse:
    canvas_state = CanvasState.model_validate(json.loads(row.canvas_state))
    config: dict[str, Any] = json.loads(row.config) if row.config else {}
    return SessionResponse(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=row.status,
        canvas_state=canvas_state,
        config=config,
    )


class SessionService:
    """CRUD + lifecycle operations for investigation sessions."""

    async def create(self, db: AsyncSession, data: SessionCreate) -> SessionResponse:
        now = _utcnow()
        session = SessionModel(
            id=str(uuid4()),
            name=data.name,
            created_at=now,
            updated_at=now,
            canvas_state=json.dumps(_EMPTY_CANVAS),
            config="{}",
            status="active",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return _row_to_response(session)

    async def get(self, db: AsyncSession, session_id: str) -> SessionResponse | None:
        result = await db.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_response(row)

    async def get_last_active(self, db: AsyncSession) -> SessionResponse | None:
        result = await db.execute(
            select(SessionModel)
            .where(SessionModel.status == "active")
            .order_by(SessionModel.updated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_response(row)

    async def list_all(self, db: AsyncSession) -> list[SessionResponse]:
        result = await db.execute(
            select(SessionModel).order_by(SessionModel.updated_at.desc())
        )
        rows = result.scalars().all()
        return [_row_to_response(r) for r in rows]

    async def update(
        self, db: AsyncSession, session_id: str, data: SessionUpdate
    ) -> SessionResponse | None:
        result = await db.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if data.name is not None:
            row.name = data.name
        if data.canvas_state is not None:
            row.canvas_state = data.canvas_state.model_dump_json()
        if data.config is not None:
            row.config = json.dumps(data.config)
        row.updated_at = _utcnow()
        await db.commit()
        await db.refresh(row)
        return _row_to_response(row)

    async def delete(self, db: AsyncSession, session_id: str) -> bool:
        result = await db.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True

    async def reset(self, db: AsyncSession, session_id: str) -> SessionResponse | None:
        """Clear canvas state but keep findings."""
        result = await db.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.canvas_state = json.dumps(_EMPTY_CANVAS)
        row.updated_at = _utcnow()
        await db.commit()
        await db.refresh(row)
        return _row_to_response(row)
