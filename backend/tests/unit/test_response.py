"""Tests for the API response envelope helpers."""

from __future__ import annotations

import uuid

from app.utils.response import envelope, error_response


class TestEnvelope:
    def test_envelope_shape(self) -> None:
        result = envelope({"key": "value"})
        assert result["data"] == {"key": "value"}
        assert result["warnings"] == []
        assert "request_id" in result["meta"]
        assert "duration_ms" in result["meta"]

    def test_request_id_is_uuid(self) -> None:
        result = envelope(None)
        # Should not raise
        uuid.UUID(result["meta"]["request_id"])

    def test_duration_ms_defaults_to_zero(self) -> None:
        result = envelope(None)
        assert result["meta"]["duration_ms"] == 0

    def test_warnings_included(self) -> None:
        result = envelope("data", warnings=["w1", "w2"])
        assert result["warnings"] == ["w1", "w2"]

    def test_none_warnings_become_empty_list(self) -> None:
        result = envelope("data", warnings=None)
        assert result["warnings"] == []

    def test_data_can_be_any_type(self) -> None:
        for data in [None, 42, "str", [1, 2], {"a": 1}]:
            result = envelope(data)
            assert result["data"] == data

    def test_unique_request_ids(self) -> None:
        ids = {envelope(None)["meta"]["request_id"] for _ in range(10)}
        assert len(ids) == 10


class TestErrorResponse:
    def test_error_shape(self) -> None:
        result = error_response("NOT_FOUND", "Session not found")
        assert result["error"]["code"] == "NOT_FOUND"
        assert result["error"]["message"] == "Session not found"
        assert "detail" not in result["error"]
        assert "request_id" in result["meta"]

    def test_error_request_id_is_uuid(self) -> None:
        result = error_response("ERR", "msg")
        uuid.UUID(result["meta"]["request_id"])

    def test_error_with_detail(self) -> None:
        detail = {"requested": 20, "remaining": 10}
        result = error_response("GUARDRAIL_EXCEEDED", "Over limit", detail)
        assert result["error"]["detail"] == detail

    def test_error_without_detail(self) -> None:
        result = error_response("ERR", "msg", detail=None)
        assert "detail" not in result["error"]
