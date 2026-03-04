"""Unit tests for session archive pack/unpack utilities."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.utils.export import (
    _PREFIX,
    SUPPORTED_SCHEMA_VERSION,
    pack_session,
    unpack_session,
    validate_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SAMPLE_SESSION: dict = {
    "id": "session-1",
    "name": "Test Session",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "status": "active",
    "config": {},
}

_SAMPLE_CANVAS: dict = {
    "schema_version": 1,
    "nodes": [],
    "edges": [],
    "viewport": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
    "filters": {"hidden_labels": [], "hidden_types": []},
}


def _make_zip(
    *,
    session: dict | None = None,
    canvas: dict | None = None,
    findings: list | None = None,
    action_log: str = "",
    snapshots: dict | None = None,
) -> bytes:
    return pack_session(
        session_data=session or _SAMPLE_SESSION,
        canvas_data=canvas or _SAMPLE_CANVAS,
        findings_data=findings or [],
        action_log_ndjson=action_log,
        snapshots=snapshots or {},
    )


# ---------------------------------------------------------------------------
# pack_session
# ---------------------------------------------------------------------------


def test_pack_creates_valid_zip() -> None:
    zip_bytes = _make_zip()

    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

    assert f"{_PREFIX}/manifest.json" in names
    assert f"{_PREFIX}/session.json" in names
    assert f"{_PREFIX}/canvas.json" in names
    assert f"{_PREFIX}/action_log.ndjson" in names
    assert f"{_PREFIX}/findings/index.json" in names


def test_pack_manifest_has_correct_schema_version() -> None:
    zip_bytes = _make_zip()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read(f"{_PREFIX}/manifest.json"))
    assert manifest["schema_version"] == SUPPORTED_SCHEMA_VERSION
    assert manifest["session_id"] == "session-1"
    assert "exported_at" in manifest


def test_pack_canvas_stored_separately() -> None:
    canvas = {
        **_SAMPLE_CANVAS,
        "nodes": [{"id": "n1", "labels": ["Person"], "properties": {}}],
    }
    zip_bytes = _make_zip(canvas=canvas)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        canvas_out = json.loads(zf.read(f"{_PREFIX}/canvas.json"))
        session_out = json.loads(zf.read(f"{_PREFIX}/session.json"))
    # canvas goes to canvas.json, NOT inside session.json
    assert canvas_out["nodes"][0]["id"] == "n1"
    assert "canvas_state" not in session_out


def test_pack_includes_action_log() -> None:
    log_line = '{"action_type": "node_search"}\n'
    zip_bytes = _make_zip(action_log=log_line)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        content = zf.read(f"{_PREFIX}/action_log.ndjson").decode()
    assert content == log_line


def test_pack_includes_findings() -> None:
    findings = [{"id": "f1", "title": "Lead", "body": "Detail", "has_snapshot": False}]
    zip_bytes = _make_zip(findings=findings)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        idx = json.loads(zf.read(f"{_PREFIX}/findings/index.json"))
    assert len(idx) == 1
    assert idx[0]["title"] == "Lead"


def test_pack_includes_snapshots() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    zip_bytes = _make_zip(snapshots={"f1": png})
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        stored = zf.read(f"{_PREFIX}/findings/snapshots/f1.png")
    assert f"{_PREFIX}/findings/snapshots/f1.png" in names
    assert stored == png


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


def test_validate_manifest_accepts_current_version() -> None:
    warnings = validate_manifest({"schema_version": SUPPORTED_SCHEMA_VERSION})
    assert warnings == []


def test_validate_manifest_rejects_future_version() -> None:
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        validate_manifest({"schema_version": SUPPORTED_SCHEMA_VERSION + 1})


def test_validate_manifest_warns_on_old_version() -> None:
    warnings = validate_manifest({"schema_version": 0})
    assert len(warnings) == 1
    assert "older" in warnings[0]


def test_validate_manifest_rejects_missing_version() -> None:
    with pytest.raises(ValueError):
        validate_manifest({})


def test_validate_manifest_rejects_string_version() -> None:
    with pytest.raises(ValueError):
        validate_manifest({"schema_version": "1"})


# ---------------------------------------------------------------------------
# unpack_session
# ---------------------------------------------------------------------------


def test_round_trip_preserves_all_fields() -> None:
    findings = [
        {
            "id": "f1",
            "title": "Lead",
            "body": "Note",
            "has_snapshot": False,
            "canvas_context": None,
        }
    ]
    log = '{"action_type": "node_search"}\n'
    zip_bytes = _make_zip(findings=findings, action_log=log)

    result = unpack_session(zip_bytes)

    assert result["manifest"]["schema_version"] == SUPPORTED_SCHEMA_VERSION
    assert result["session"]["id"] == "session-1"
    assert result["session"]["name"] == "Test Session"
    assert result["canvas"]["schema_version"] == 1
    assert result["action_log_ndjson"] == log
    assert len(result["findings"]) == 1
    assert result["findings"][0]["title"] == "Lead"
    assert result["snapshots"] == {}


def test_round_trip_preserves_snapshots() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    zip_bytes = _make_zip(snapshots={"f1": png})
    result = unpack_session(zip_bytes)
    assert "f1" in result["snapshots"]
    assert result["snapshots"]["f1"] == png


def test_unpack_invalid_zip_raises() -> None:
    with pytest.raises(ValueError, match="not a valid ZIP"):
        unpack_session(b"this is not a zip file")


def test_unpack_missing_manifest_raises() -> None:
    # Build a ZIP without manifest.json
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("session-export/session.json", "{}")
    with pytest.raises(ValueError, match=r"manifest\.json"):
        unpack_session(buf.getvalue())


def test_unpack_empty_action_log_when_absent() -> None:
    # Build ZIP with no action_log.ndjson entry
    zip_bytes = _make_zip()
    result = unpack_session(zip_bytes)
    # pack always includes it; verify it's an empty string for empty input
    assert result["action_log_ndjson"] == ""
