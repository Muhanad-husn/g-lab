"""Dual-sink action logger.

Every action writes to:
  1. NDJSON file at {GLAB_DATA_DIR}/sessions/{session_id}/action_log.ndjson
     (append-only; source of truth for exports)
  2. SQLite action_log table (for in-app querying)

Both writes happen in a single async background task. A failure in either
sink is logged but never propagates — the request has already returned.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.models.db import ActionLog
from app.models.enums import ActionType

logger: Any = get_logger(__name__)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _build_entry(
    session_id: str,
    action_type: ActionType | str,
    actor: str,
    payload: dict[str, Any] | None,
    result_summary: dict[str, Any] | None,
    guardrail_warnings: list[str] | None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "session_id": session_id,
        "timestamp": _utcnow(),
        "action_type": str(action_type),
        "actor": actor,
        "payload": payload,
        "result_summary": result_summary,
        "guardrail_warnings": guardrail_warnings or [],
    }


def _append_ndjson(path: Path, entry: dict[str, Any]) -> None:
    """Sync file append — called via asyncio.to_thread."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


class ActionLogger:
    """Writes action entries to both NDJSON and SQLite."""

    def __init__(
        self,
        data_dir: Path,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._data_dir = data_dir
        self._session_factory = session_factory

    def _ndjson_path(self, session_id: str) -> Path:
        return self._data_dir / "sessions" / session_id / "action_log.ndjson"

    async def _write_sqlite(
        self,
        entry: dict[str, Any],
        session_id: str,
        actor: str,
        payload: dict[str, Any] | None,
        result_summary: dict[str, Any] | None,
        guardrail_warnings: list[str] | None,
    ) -> None:
        """Write a single action log row to SQLite."""
        async with self._session_factory() as db:
            row = ActionLog(
                id=entry["id"],
                session_id=session_id,
                timestamp=entry["timestamp"],
                action_type=entry["action_type"],
                actor=actor,
                payload=json.dumps(payload) if payload else None,
                result_summary=(
                    json.dumps(result_summary) if result_summary else None
                ),
                guardrail_warnings=(
                    json.dumps(guardrail_warnings) if guardrail_warnings else None
                ),
            )
            db.add(row)
            await db.commit()

    async def log(
        self,
        session_id: str,
        action_type: ActionType | str,
        actor: str = "user",
        payload: dict[str, Any] | None = None,
        result_summary: dict[str, Any] | None = None,
        guardrail_warnings: list[str] | None = None,
    ) -> None:
        """Write one log entry to both sinks (fire-and-forget from router)."""
        entry = _build_entry(
            session_id=session_id,
            action_type=action_type,
            actor=actor,
            payload=payload,
            result_summary=result_summary,
            guardrail_warnings=guardrail_warnings,
        )

        # Sink 1: NDJSON file (source of truth)
        try:
            await asyncio.to_thread(
                _append_ndjson, self._ndjson_path(session_id), entry
            )
        except Exception as exc:
            logger.warning(
                "action_log.ndjson_write_failed",
                session_id=session_id,
                error=str(exc),
            )

        # Sink 2: SQLite
        # Shield from cancellation: when the SSE client disconnects, Starlette
        # cancels the request scope (including BackgroundTasks).  The NDJSON
        # write survives (runs in a thread), but the async SQLite write would
        # lose the connection mid-commit.  asyncio.shield lets the inner task
        # run to completion even when the outer task is cancelled.
        try:
            await asyncio.shield(
                self._write_sqlite(entry, session_id, actor, payload,
                                   result_summary, guardrail_warnings)
            )
        except asyncio.CancelledError:
            pass  # inner task still completes; suppress outer cancellation
        except Exception as exc:
            logger.warning(
                "action_log.sqlite_write_failed",
                session_id=session_id,
                error=str(exc),
            )
