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
