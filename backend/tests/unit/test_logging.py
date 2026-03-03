"""Tests for app.core.logging."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import structlog

from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    unbind_request_context,
)


def _reconfigure(level: str = "INFO") -> None:
    """Helper: reset structlog and reconfigure."""
    structlog.reset_defaults()
    configure_logging(log_level=level)


class TestConfigureLogging:
    """Tests for configure_logging()."""

    def test_configures_without_error(self) -> None:
        _reconfigure("INFO")

    def test_accepts_debug_level(self) -> None:
        _reconfigure("DEBUG")

    def test_accepts_warning_level(self) -> None:
        _reconfigure("WARNING")

    def test_accepts_error_level(self) -> None:
        _reconfigure("ERROR")

    def test_case_insensitive_level(self) -> None:
        _reconfigure("info")

    def test_json_output_at_info(self) -> None:
        """INFO level should produce JSON lines."""
        _reconfigure("INFO")
        buf = io.StringIO()
        with patch("structlog.PrintLoggerFactory") as mock_factory:
            # Reconfigure with our buffer
            structlog.reset_defaults()
            configure_logging("INFO")

        # Just verify it configured without error — output format is
        # validated by checking the renderer in the processor chain.
        logger = get_logger("test")
        assert logger is not None

    def test_debug_uses_console_renderer(self) -> None:
        """DEBUG level should use ConsoleRenderer."""
        _reconfigure("DEBUG")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        renderer = processors[-1]
        assert isinstance(renderer, structlog.dev.ConsoleRenderer)

    def test_info_uses_json_renderer(self) -> None:
        """INFO level should use JSONRenderer."""
        _reconfigure("INFO")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        renderer = processors[-1]
        assert isinstance(renderer, structlog.processors.JSONRenderer)

    def test_processors_include_timestamper(self) -> None:
        _reconfigure("INFO")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        has_timestamper = any(
            isinstance(p, structlog.processors.TimeStamper) for p in processors
        )
        assert has_timestamper

    def test_processors_include_log_level(self) -> None:
        _reconfigure("INFO")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        assert structlog.stdlib.add_log_level in processors

    def test_json_path_includes_format_exc_info(self) -> None:
        """JSON path must convert exc_info tuples before JSONRenderer runs."""
        _reconfigure("INFO")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        assert structlog.processors.format_exc_info in processors

    def test_debug_path_excludes_format_exc_info(self) -> None:
        """DEBUG path omits format_exc_info so ConsoleRenderer keeps native coloring."""
        _reconfigure("DEBUG")
        cfg = structlog.get_config()
        processors = cfg["processors"]
        assert structlog.processors.format_exc_info not in processors

    def test_json_exc_info_is_serializable(self) -> None:
        """logger.error(..., exc_info=True) must produce valid JSON — not raise TypeError."""
        buf = io.StringIO()
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.UnicodeDecoder(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=buf),
            cache_logger_on_first_use=False,
        )
        logger = structlog.get_logger("exc_test")
        try:
            raise ValueError("copilot pipeline timeout")
        except ValueError:
            logger.error("pipeline failed", exc_info=True)

        data = json.loads(buf.getvalue().strip())
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "copilot pipeline timeout" in data["exception"]


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_bound_logger(self) -> None:
        _reconfigure("INFO")
        logger = get_logger("mymodule")
        assert logger is not None

    def test_logger_with_initial_context(self) -> None:
        _reconfigure("INFO")
        logger = get_logger("mymodule", component="neo4j")
        assert logger is not None

    def test_logger_produces_output(self) -> None:
        """Ensure logger.info() writes to stderr without raising."""
        _reconfigure("INFO")
        buf = io.StringIO()
        logger = structlog.get_logger("test_output")
        # Bind a fresh logger with our own output
        # Just verify no exceptions are raised
        logger.info("test message", key="value")


class TestRequestContext:
    """Tests for bind_request_context / clear_request_context."""

    def test_bind_and_clear_no_error(self) -> None:
        _reconfigure("INFO")
        clear_request_context()
        bind_request_context(request_id="abc-123", method="GET", path="/test")
        clear_request_context()

    def test_context_appears_in_log_output(self) -> None:
        """Bound context vars should appear in the rendered log entry."""
        _reconfigure("INFO")
        clear_request_context()
        bind_request_context(request_id="req-42")

        buf = io.StringIO()
        # Create a logger that writes to our buffer
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=buf),
            cache_logger_on_first_use=False,
        )

        logger = structlog.get_logger("ctx_test")
        logger.info("hello")

        output = buf.getvalue().strip()
        data = json.loads(output)
        assert data["request_id"] == "req-42"
        assert data["event"] == "hello"

        clear_request_context()

    def test_clear_removes_context(self) -> None:
        """After clear, previously bound vars should not appear."""
        _reconfigure("INFO")
        bind_request_context(request_id="old-id")
        clear_request_context()

        buf = io.StringIO()
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=buf),
            cache_logger_on_first_use=False,
        )

        logger = structlog.get_logger("clear_test")
        logger.info("after_clear")

        output = buf.getvalue().strip()
        data = json.loads(output)
        assert "request_id" not in data

    def test_unbind_removes_specific_key(self) -> None:
        """unbind_request_context removes the named key from the context."""
        clear_request_context()
        bind_request_context(request_id="req-1", pipeline_stage="router")

        buf = io.StringIO()
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=buf),
            cache_logger_on_first_use=False,
        )

        unbind_request_context("pipeline_stage")
        structlog.get_logger("unbind_test").info("after unbind")

        data = json.loads(buf.getvalue().strip())
        assert "pipeline_stage" not in data

    def test_unbind_preserves_other_keys(self) -> None:
        """unbind_request_context does not wipe the rest of the context."""
        clear_request_context()
        bind_request_context(request_id="req-2", pipeline_stage="synthesiser", model="opus")

        buf = io.StringIO()
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=buf),
            cache_logger_on_first_use=False,
        )

        # Simulate end-of-stage cleanup: drop stage keys, keep request context.
        unbind_request_context("pipeline_stage", "model")
        structlog.get_logger("preserve_test").info("next stage")

        data = json.loads(buf.getvalue().strip())
        assert data["request_id"] == "req-2"
        assert "pipeline_stage" not in data
        assert "model" not in data

        clear_request_context()
