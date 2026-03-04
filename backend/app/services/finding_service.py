"""Finding CRUD service.

Snapshots are stored as raw bytes (PNG) in the DB BLOB column.
has_snapshot is computed from whether snapshot_png is non-None.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Finding as FindingModel
from app.models.schemas import FindingCreate, FindingResponse, FindingUpdate


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_response(row: FindingModel) -> FindingResponse:
    canvas_context: list[str] | None = None
    if row.canvas_context:
        canvas_context = json.loads(row.canvas_context)
    return FindingResponse(
        id=row.id,
        session_id=row.session_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        title=row.title,
        body=row.body,
        has_snapshot=row.snapshot_png is not None,
        canvas_context=canvas_context,
    )


class FindingService:
    """CRUD operations for durable investigative findings."""

    async def list_for_session(
        self, db: AsyncSession, session_id: str
    ) -> list[FindingResponse]:
        result = await db.execute(
            select(FindingModel)
            .where(FindingModel.session_id == session_id)
            .order_by(FindingModel.created_at.asc())
        )
        rows = result.scalars().all()
        return [_row_to_response(r) for r in rows]

    async def create(
        self, db: AsyncSession, session_id: str, data: FindingCreate
    ) -> FindingResponse:
        snapshot_bytes: bytes | None = None
        if data.snapshot_png:
            snapshot_bytes = base64.b64decode(data.snapshot_png)

        canvas_context_json: str | None = None
        if data.canvas_context is not None:
            canvas_context_json = json.dumps(data.canvas_context)

        now = _utcnow()
        finding = FindingModel(
            id=str(uuid4()),
            session_id=session_id,
            created_at=now,
            updated_at=now,
            title=data.title,
            body=data.body,
            snapshot_png=snapshot_bytes,
            canvas_context=canvas_context_json,
        )
        db.add(finding)
        await db.commit()
        await db.refresh(finding)
        return _row_to_response(finding)

    async def get(
        self, db: AsyncSession, session_id: str, finding_id: str
    ) -> FindingResponse | None:
        result = await db.execute(
            select(FindingModel).where(
                FindingModel.id == finding_id,
                FindingModel.session_id == session_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_response(row)

    async def update(
        self, db: AsyncSession, session_id: str, finding_id: str, data: FindingUpdate
    ) -> FindingResponse | None:
        result = await db.execute(
            select(FindingModel).where(
                FindingModel.id == finding_id,
                FindingModel.session_id == session_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if data.title is not None:
            row.title = data.title
        if data.body is not None:
            row.body = data.body
        row.updated_at = _utcnow()
        await db.commit()
        await db.refresh(row)
        return _row_to_response(row)

    async def delete(self, db: AsyncSession, session_id: str, finding_id: str) -> bool:
        result = await db.execute(
            select(FindingModel).where(
                FindingModel.id == finding_id,
                FindingModel.session_id == session_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True
