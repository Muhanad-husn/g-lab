"""Tests for app.core.monitoring."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY, MagicMock, call

import pytest
import structlog

from app.core.logging import configure_logging
from app.core.monitoring import (
    Neo4jStatus,
    Neo4jStatusTracker,
    OperationTimer,
    WarningCollector,
)


def _reconfigure(level: str = "DEBUG") -> None:
    """Reset structlog and reconfigure at the given level."""
    structlog.reset_defaults()
    configure_logging(log_level=level)


# ---------------------------------------------------------------------------
# OperationTimer
# ---------------------------------------------------------------------------


class TestOperationTimerSuccess:
    """Happy-path tests for OperationTimer."""

    @pytest.mark.asyncio
    async def test_emits_start_and_complete(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer("neo4j.search", logger=log, query="test"):
            pass

        assert log.info.call_count == 2
        start_call = log.info.call_args_list[0]
        assert start_call == call(
            "op.start", operation="neo4j.search", query="test"
        )
        complete_call = log.info.call_args_list[1]
        assert complete_call[0][0] == "op.complete"
        assert complete_call[1]["operation"] == "neo4j.search"
        assert "duration_ms" in complete_call[1]
        assert complete_call[1]["query"] == "test"

    @pytest.mark.asyncio
    async def test_duration_ms_is_positive(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer("test.op", logger=log):
            await asyncio.sleep(0.01)

        complete_call = log.info.call_args_list[1]
        duration = complete_call[1]["duration_ms"]
        assert duration > 0

    @pytest.mark.asyncio
    async def test_set_result_included_in_complete(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer("neo4j.expand", logger=log) as op:
            op.set_result(nodes=42, edges=15)

        complete_call = log.info.call_args_list[1]
        assert complete_call[1]["nodes"] == 42
        assert complete_call[1]["edges"] == 15

    @pytest.mark.asyncio
    async def test_set_result_multiple_calls_merge(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer("test.multi", logger=log) as op:
            op.set_result(a=1)
            op.set_result(b=2)

        complete_call = log.info.call_args_list[1]
        assert complete_call[1]["a"] == 1
        assert complete_call[1]["b"] == 2

    @pytest.mark.asyncio
    async def test_metadata_passes_through(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer(
            "neo4j.connect", logger=log, attempt=3, uri="bolt://localhost"
        ):
            pass

        start_call = log.info.call_args_list[0]
        assert start_call[1]["attempt"] == 3
        assert start_call[1]["uri"] == "bolt://localhost"

    @pytest.mark.asyncio
    async def test_duration_ms_property_during_operation(self) -> None:
        _reconfigure()
        log = MagicMock()

        async with OperationTimer("test.prop", logger=log) as op:
            await asyncio.sleep(0.01)
            mid_duration = op.duration_ms
            assert mid_duration > 0

    @pytest.mark.asyncio
    async def test_duration_ms_property_before_entry(self) -> None:
        _reconfigure()
        op = OperationTimer("test.pre", logger=MagicMock())
        assert op.duration_ms == 0.0


class TestOperationTimerError:
    """Error-path tests for OperationTimer."""

    @pytest.mark.asyncio
    async def test_emits_error_on_exception(self) -> None:
        _reconfigure()
        log = MagicMock()

        with pytest.raises(ValueError, match="boom"):
            async with OperationTimer("test.fail", logger=log):
                raise ValueError("boom")

        # op.start logged via info, op.error logged via error
        log.info.assert_called_once()
        log.error.assert_called_once()
        error_call = log.error.call_args
        assert error_call[0][0] == "op.error"
        assert error_call[1]["operation"] == "test.fail"
        assert error_call[1]["error"] == "boom"
        assert error_call[1]["error_type"] == "ValueError"
        assert "duration_ms" in error_call[1]

    @pytest.mark.asyncio
    async def test_does_not_suppress_exception(self) -> None:
        _reconfigure()

        with pytest.raises(RuntimeError):
            async with OperationTimer("test.nosup", logger=MagicMock()):
                raise RuntimeError("propagated")

    @pytest.mark.asyncio
    async def test_error_includes_metadata(self) -> None:
        _reconfigure()
        log = MagicMock()

        with pytest.raises(TypeError):
            async with OperationTimer(
                "neo4j.query", logger=log, query="MATCH (n)"
            ):
                raise TypeError("bad type")

        error_call = log.error.call_args
        assert error_call[1]["query"] == "MATCH (n)"

    @pytest.mark.asyncio
    async def test_error_duration_is_positive(self) -> None:
        _reconfigure()
        log = MagicMock()

        with pytest.raises(Exception):
            async with OperationTimer("test.dur", logger=log):
                await asyncio.sleep(0.01)
                raise Exception("fail")

        error_call = log.error.call_args
        assert error_call[1]["duration_ms"] > 0


class TestOperationTimerDefaultLogger:
    """Test that OperationTimer works without an explicit logger."""

    @pytest.mark.asyncio
    async def test_uses_default_logger(self) -> None:
        _reconfigure()
        # Should not raise — uses get_logger("monitoring") internally
        async with OperationTimer("test.default") as op:
            op.set_result(ok=True)


# ---------------------------------------------------------------------------
# WarningCollector
# ---------------------------------------------------------------------------


class TestWarningCollector:
    """Tests for WarningCollector."""

    def setup_method(self) -> None:
        WarningCollector.clear()

    def teardown_method(self) -> None:
        WarningCollector.clear()

    def test_get_all_empty_by_default(self) -> None:
        assert WarningCollector.get_all() == []

    def test_add_single_warning(self) -> None:
        WarningCollector.add("approaching limit")
        assert WarningCollector.get_all() == ["approaching limit"]

    def test_add_multiple_warnings(self) -> None:
        WarningCollector.add("warn 1")
        WarningCollector.add("warn 2")
        WarningCollector.add("warn 3")
        assert WarningCollector.get_all() == ["warn 1", "warn 2", "warn 3"]

    def test_clear_resets(self) -> None:
        WarningCollector.add("will be cleared")
        WarningCollector.clear()
        assert WarningCollector.get_all() == []

    def test_add_after_clear(self) -> None:
        WarningCollector.add("before")
        WarningCollector.clear()
        WarningCollector.add("after")
        assert WarningCollector.get_all() == ["after"]

    def test_get_all_returns_copy_semantics(self) -> None:
        """get_all returns the internal list — verify it reflects adds."""
        WarningCollector.add("first")
        result1 = WarningCollector.get_all()
        WarningCollector.add("second")
        result2 = WarningCollector.get_all()
        assert len(result2) == 2

    @pytest.mark.asyncio
    async def test_isolation_between_tasks(self) -> None:
        """Each asyncio task gets its own context variable copy."""
        results: dict[str, list[str]] = {}

        async def task_a() -> None:
            WarningCollector.clear()
            WarningCollector.add("from task A")
            await asyncio.sleep(0.01)
            results["a"] = WarningCollector.get_all()

        async def task_b() -> None:
            WarningCollector.clear()
            WarningCollector.add("from task B")
            await asyncio.sleep(0.01)
            results["b"] = WarningCollector.get_all()

        await asyncio.gather(task_a(), task_b())

        assert results["a"] == ["from task A"]
        assert results["b"] == ["from task B"]

    @pytest.mark.asyncio
    async def test_clear_does_not_affect_other_tasks(self) -> None:
        """Clearing in one task doesn't affect another."""
        results: dict[str, list[str]] = {}
        barrier = asyncio.Event()

        async def task_writer() -> None:
            WarningCollector.clear()
            WarningCollector.add("persistent")
            barrier.set()
            await asyncio.sleep(0.02)
            results["writer"] = WarningCollector.get_all()

        async def task_clearer() -> None:
            await barrier.wait()
            WarningCollector.clear()
            results["clearer"] = WarningCollector.get_all()

        await asyncio.gather(task_writer(), task_clearer())

        assert results["writer"] == ["persistent"]
        assert results["clearer"] == []


# ---------------------------------------------------------------------------
# Neo4jStatusTracker
# ---------------------------------------------------------------------------


class TestNeo4jStatusTracker:
    """Tests for Neo4jStatusTracker."""

    def test_initial_status_is_disconnected(self) -> None:
        tracker = Neo4jStatusTracker()
        assert tracker.status == Neo4jStatus.DISCONNECTED

    def test_is_available_false_when_disconnected(self) -> None:
        tracker = Neo4jStatusTracker()
        assert tracker.is_available is False

    def test_update_to_connected(self) -> None:
        tracker = Neo4jStatusTracker()
        tracker.update(Neo4jStatus.CONNECTED, reason="startup")
        assert tracker.status == Neo4jStatus.CONNECTED
        assert tracker.is_available is True

    def test_update_to_degraded(self) -> None:
        tracker = Neo4jStatusTracker()
        tracker.update(Neo4jStatus.DEGRADED, reason="timeout")
        assert tracker.status == Neo4jStatus.DEGRADED
        assert tracker.is_available is False

    def test_same_status_is_noop(self) -> None:
        _reconfigure()
        log = MagicMock()
        tracker = Neo4jStatusTracker()
        tracker._log = log

        tracker.update(Neo4jStatus.DISCONNECTED)
        log.info.assert_not_called()

    def test_status_change_logs_event(self) -> None:
        _reconfigure()
        log = MagicMock()
        tracker = Neo4jStatusTracker()
        tracker._log = log

        tracker.update(Neo4jStatus.CONNECTED, reason="retry success")

        log.info.assert_called_once_with(
            "neo4j.status_change",
            old_status="disconnected",
            new_status="connected",
            reason="retry success",
        )

    def test_multiple_transitions(self) -> None:
        tracker = Neo4jStatusTracker()

        tracker.update(Neo4jStatus.CONNECTED, reason="startup")
        assert tracker.status == Neo4jStatus.CONNECTED

        tracker.update(Neo4jStatus.DEGRADED, reason="pool exhausted")
        assert tracker.status == Neo4jStatus.DEGRADED

        tracker.update(Neo4jStatus.DISCONNECTED, reason="driver closed")
        assert tracker.status == Neo4jStatus.DISCONNECTED

    def test_status_enum_values(self) -> None:
        assert Neo4jStatus.CONNECTED.value == "connected"
        assert Neo4jStatus.DEGRADED.value == "degraded"
        assert Neo4jStatus.DISCONNECTED.value == "disconnected"

    def test_status_is_str_enum(self) -> None:
        """Neo4jStatus is a str enum — serialises directly to JSON."""
        assert isinstance(Neo4jStatus.CONNECTED, str)
        assert Neo4jStatus.CONNECTED == "connected"

    def test_update_without_reason(self) -> None:
        _reconfigure()
        log = MagicMock()
        tracker = Neo4jStatusTracker()
        tracker._log = log

        tracker.update(Neo4jStatus.CONNECTED)

        log.info.assert_called_once_with(
            "neo4j.status_change",
            old_status="disconnected",
            new_status="connected",
            reason="",
        )
