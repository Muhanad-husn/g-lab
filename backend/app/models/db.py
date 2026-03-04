"""SQLAlchemy async ORM models and engine factory.

All IDs are TEXT (UUIDs as strings). Datetimes are ISO-8601 TEXT.
Canvas state and config are TEXT columns holding JSON, serialized
via Pydantic on the service layer.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text, event
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all ORM models."""


_EMPTY_CANVAS: str = json.dumps(
    {
        "schema_version": 1,
        "nodes": [],
        "edges": [],
        "viewport": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        "filters": {"hidden_labels": [], "hidden_types": []},
    }
)


class Session(Base):
    """Investigation session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    preset_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    canvas_state: Mapped[str] = mapped_column(
        Text, nullable=False, default=_EMPTY_CANVAS
    )
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")


class Finding(Base):
    """Durable investigative finding attached to a session."""

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_png: Mapped[bytes | None] = mapped_column(nullable=True)
    canvas_context: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActionLog(Base):
    """Logged user/system action within a session."""

    __tablename__ = "action_log"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)


class Preset(Base):
    """Copilot configuration preset."""

    __tablename__ = "presets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[int] = mapped_column(default=0)
    config: Mapped[str] = mapped_column(Text, nullable=False)


class ConversationMessage(Base):
    """Copilot conversation message within a session."""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(
        "metadata", Text, nullable=True
    )


def _set_wal_mode(dbapi_conn: Any, _connection_record: Any) -> None:
    """Enable WAL journal mode for SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_engine(database_url: str) -> Any:
    """Create an async SQLAlchemy engine with WAL mode enabled."""
    engine = create_async_engine(database_url, echo=False)
    event.listen(engine.sync_engine, "connect", _set_wal_mode)
    return engine


def create_session_factory(
    engine: Any,
) -> async_sessionmaker:  # type: ignore[type-arg]
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
