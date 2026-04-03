"""Conversation history service for Copilot sessions.

Persists user/assistant messages in the ``conversation_messages`` table
and provides retrieval, conversation listing, and switching operations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ConversationMessage
from app.models.schemas import ConversationSummary, CopilotMessage


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
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> CopilotMessage:
        """Persist a single message and return its schema representation."""
        msg = ConversationMessage(
            id=str(uuid4()),
            session_id=session_id,
            conversation_id=conversation_id,
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
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[CopilotMessage]:
        """Return the most recent *limit* messages for a conversation.

        If *conversation_id* is None, returns messages from the latest
        conversation in the session.
        """
        if conversation_id is None:
            conversation_id = await self.get_active_conversation_id(db, session_id)
            if conversation_id is None:
                return []

        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.session_id == session_id,
                ConversationMessage.conversation_id == conversation_id,
            )
            .order_by(ConversationMessage.timestamp.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_to_schema(r) for r in rows]

    async def get_active_conversation_id(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> str | None:
        """Return the most recent conversation_id for a session, or None."""
        stmt = (
            select(ConversationMessage.conversation_id)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def list_conversations(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> list[ConversationSummary]:
        """List all conversations for a session, newest first.

        Each summary includes the first user message as a preview.
        """
        # Get conversation_id, min timestamp, count per conversation
        stmt = (
            select(
                ConversationMessage.conversation_id,
                func.min(ConversationMessage.timestamp).label("created_at"),
                func.count().label("message_count"),
            )
            .where(ConversationMessage.session_id == session_id)
            .group_by(ConversationMessage.conversation_id)
            .order_by(func.min(ConversationMessage.timestamp).desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        summaries: list[ConversationSummary] = []
        for row in rows:
            conv_id = row[0]
            created_at = row[1]
            message_count = row[2]

            # Fetch first user message as preview
            preview_stmt = (
                select(ConversationMessage.content)
                .where(
                    ConversationMessage.session_id == session_id,
                    ConversationMessage.conversation_id == conv_id,
                    ConversationMessage.role == "user",
                )
                .order_by(ConversationMessage.timestamp.asc())
                .limit(1)
            )
            preview_result = await db.execute(preview_stmt)
            preview_text = preview_result.scalar_one_or_none() or ""
            # Truncate preview
            if len(preview_text) > 100:
                preview_text = preview_text[:100] + "…"

            summaries.append(
                ConversationSummary(
                    id=conv_id,
                    session_id=session_id,
                    created_at=created_at,
                    preview=preview_text,
                    message_count=message_count,
                )
            )

        return summaries

    async def start_new_conversation(
        self,
        session_id: str,
    ) -> str:
        """Generate a new conversation ID. No DB write needed — the first
        message saved with this ID creates the conversation implicitly."""
        return str(uuid4())

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
        conversation_id=msg.conversation_id,
        role=msg.role,
        content=msg.content,
        timestamp=msg.timestamp,
        metadata=meta,
    )
