"""Structured logging configuration via structlog.

Usage::

    # Once at startup (main.py lifespan):
    configure_logging(log_level="INFO")

    # Any module:
    logger = get_logger(__name__)
    logger.info("connecting", uri=uri)

    # Request middleware:
    clear_request_context()
    bind_request_context(request_id=rid, method="GET", path="/api/v1/…")

    # Pipeline stages (Phase 2) — bind without clobbering the request context:
    bind_request_context(pipeline_stage="router", model="claude-haiku-4-5")
    # … log entries here carry pipeline_stage and model …
    unbind_request_context("pipeline_stage", "model")
"""

from __future__ import annotations

import sys
from typing import Any

import structlog
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    unbind_contextvars,
)

__all__ = [
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "get_logger",
    "unbind_request_context",
]


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog processors and output format.

    Call once during application startup.

    * **INFO+** → JSON lines to stderr (production / Docker).
    * **DEBUG** → Colored console output to stderr (development).
    """
    level = log_level.upper()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if level == "DEBUG":
        # ConsoleRenderer handles exc_info natively (coloured tracebacks).
        final_processors: list[structlog.types.Processor] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        # format_exc_info converts (type, value, tb) tuples to a plain string
        # before JSONRenderer runs; without it, json.dumps raises TypeError on
        # any logger.exception() / logger.error(..., exc_info=True) call.
        final_processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=final_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: Any) -> Any:
    """Return a bound logger, optionally with initial key-value context."""
    return structlog.get_logger(name, **initial_context)


def bind_request_context(**kwargs: Any) -> None:
    """Bind key-value pairs to the request-scoped context (contextvars)."""
    bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """Clear all request-scoped context (call at request start)."""
    clear_contextvars()


def unbind_request_context(*keys: str) -> None:
    """Remove specific keys from the request-scoped context.

    Use this to clean up pipeline-stage bindings (e.g. ``pipeline_stage``,
    ``model``) between steps without wiping the entire request context
    (``request_id``, ``session_id``, etc.).

    Example::

        bind_request_context(pipeline_stage="router", model="claude-haiku-4-5")
        # … log entries carry pipeline_stage and model …
        unbind_request_context("pipeline_stage", "model")
        # request_id / session_id are still bound for the next stage
    """
    unbind_contextvars(*keys)
