"""Cross-cutting monitoring primitives.

Builds on the structlog setup in ``logging.py``.  Three primitives:

* :class:`OperationTimer` — async context manager that emits ``op.start``
  and ``op.complete`` (or ``op.error``) events with accurate ``duration_ms``.
* :class:`WarningCollector` — request-scoped warning accumulator backed by
  ``contextvars`` (same mechanism as structlog request context).
* :class:`Neo4jStatusTracker` — singleton tracking Neo4j connection state.

Usage::

    # Service method:
    async with OperationTimer("neo4j.expand", logger=self._log, node_count=3) as op:
        result = await self._execute(...)
        op.set_result(nodes=len(result))

    # Guardrail / service:
    WarningCollector.add("Approaching canvas limit (488/500 nodes)")

    # Middleware (auto-clears at request start, reads at request end):
    WarningCollector.clear()
    ...
    warnings = WarningCollector.get_all()

    # Neo4j service:
    neo4j_status.update(Neo4jStatus.CONNECTED, reason="startup")
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from enum import StrEnum
from types import TracebackType
from typing import Any

from app.core.logging import get_logger

__all__ = [
    "Neo4jStatus",
    "Neo4jStatusTracker",
    "OperationTimer",
    "WarningCollector",
]


# ---------------------------------------------------------------------------
# OperationTimer
# ---------------------------------------------------------------------------


class OperationTimer:
    """Async context manager for timing and logging operations.

    Emits structured log events via the provided (or default) structlog logger:

    * ``op.start`` — on entry, with operation name and caller-supplied metadata.
    * ``op.complete`` — on successful exit, with ``duration_ms`` and any
      result metadata set via :meth:`set_result`.
    * ``op.error`` — on exception, with ``duration_ms``, ``error``, and
      ``error_type``.

    Not a decorator — service methods call :meth:`set_result` based on actual
    results within the ``async with`` block.
    """

    __slots__ = ("_log", "_metadata", "_operation", "_result", "_start")

    def __init__(
        self,
        operation: str,
        *,
        logger: Any = None,
        **metadata: Any,
    ) -> None:
        self._operation = operation
        self._log = logger or get_logger("monitoring")
        self._metadata = metadata
        self._result: dict[str, Any] = {}
        self._start: float = 0.0

    def set_result(self, **kwargs: Any) -> None:
        """Record result metadata to include in the ``op.complete`` event."""
        self._result.update(kwargs)

    @property
    def duration_ms(self) -> float:
        """Elapsed time since context entry in milliseconds."""
        if self._start == 0.0:
            return 0.0
        return (time.monotonic() - self._start) * 1000

    async def __aenter__(self) -> OperationTimer:
        self._start = time.monotonic()
        self._log.info(
            "op.start",
            operation=self._operation,
            **self._metadata,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        elapsed = round((time.monotonic() - self._start) * 1000, 1)

        if exc_type is not None:
            self._log.error(
                "op.error",
                operation=self._operation,
                duration_ms=elapsed,
                error=str(exc_val),
                error_type=exc_type.__name__,
                **self._metadata,
            )
        else:
            self._log.info(
                "op.complete",
                operation=self._operation,
                duration_ms=elapsed,
                **self._result,
                **self._metadata,
            )
        # Never suppress exceptions
        return None


# ---------------------------------------------------------------------------
# WarningCollector
# ---------------------------------------------------------------------------

_warnings_var: ContextVar[list[str] | None] = ContextVar(
    "glab_warnings",
    default=None,
)


class WarningCollector:
    """Request-scoped warning accumulator using ``contextvars``.

    Any layer (guardrails, services, middleware) can call
    :meth:`add` to push a warning.  The response middleware reads
    :meth:`get_all` and injects the list into the envelope ``warnings``
    array, then calls :meth:`clear`.

    Thread/task safe: each asyncio task (= each request in FastAPI)
    gets its own context variable copy.
    """

    @staticmethod
    def add(message: str) -> None:
        """Append a warning message to the current request's list."""
        warnings = _warnings_var.get()
        if warnings is None:
            warnings = []
            _warnings_var.set(warnings)
        warnings.append(message)

    @staticmethod
    def get_all() -> list[str]:
        """Return all warnings collected in this request (or empty list)."""
        return _warnings_var.get() or []

    @staticmethod
    def clear() -> None:
        """Reset warnings for the current request context."""
        _warnings_var.set(None)


# ---------------------------------------------------------------------------
# Neo4jStatusTracker
# ---------------------------------------------------------------------------


class Neo4jStatus(StrEnum):
    """Neo4j connection states."""

    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class Neo4jStatusTracker:
    """Singleton-style tracker for Neo4j connection health.

    Updated reactively by ``neo4j_service`` on connect/disconnect/error.
    Read by ``/health`` endpoint and exposed to the frontend.
    """

    __slots__ = ("_log", "_status")

    def __init__(self) -> None:
        self._status = Neo4jStatus.DISCONNECTED
        self._log = get_logger("neo4j.status")

    @property
    def status(self) -> Neo4jStatus:
        """Current connection status."""
        return self._status

    @property
    def is_available(self) -> bool:
        """``True`` when Neo4j is fully connected."""
        return self._status == Neo4jStatus.CONNECTED

    def update(
        self,
        new_status: Neo4jStatus,
        *,
        reason: str = "",
    ) -> None:
        """Transition to *new_status*.  No-op if already in that state."""
        old = self._status
        if old == new_status:
            return
        self._status = new_status
        self._log.info(
            "neo4j.status_change",
            old_status=old.value,
            new_status=new_status.value,
            reason=reason,
        )
