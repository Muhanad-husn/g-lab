"""Conversation history service for Copilot sessions.

Persists user/assistant messages in the ``conversation_messages`` table
and provides retrieval and clearing operations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ConversationMessage
from app.models.schemas import CopilotMessage


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class ConversationService:
    """CRUD operations for conversation messages."""

    async def save_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> CopilotMessage:
        """Persist a single message and return its schema representation."""
        msg = ConversationMessage(
            id=str(uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            timestamp=_utcnow(),
            metadata_json=json.dumps(metadata) if metadata is not None else None,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return _to_schema(msg)

    async def get_history(
        self,
        db: AsyncSession,
        session_id: str,
        limit: int = 50,
    ) -> list[CopilotMessage]:
        """Return the most recent *limit* messages for a session, oldest first."""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.timestamp.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_to_schema(r) for r in rows]

    async def clear_history(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> int:
        """Delete all messages for *session_id*. Returns count deleted."""
        stmt = delete(ConversationMessage).where(
            ConversationMessage.session_id == session_id
        )
        result = await db.execute(stmt)
        await db.commit()
        deleted: int = getattr(result, "rowcount", 0)
        return deleted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_schema(msg: ConversationMessage) -> CopilotMessage:
    meta: dict[str, Any] | None = None
    if msg.metadata_json is not None:
        try:
            meta = json.loads(msg.metadata_json)
        except (json.JSONDecodeError, TypeError):
            meta = None
    return CopilotMessage(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        timestamp=msg.timestamp,
        metadata=meta,
    )
