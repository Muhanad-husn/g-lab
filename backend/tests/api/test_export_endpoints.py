"""API tests for session export and import endpoints.

Uses the shared `client` fixture from conftest.py (in-memory SQLite,
minimal FastAPI app with sessions + findings routers mounted).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from httpx import AsyncClient

from app.utils.export import _PREFIX, pack_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_CANVAS = {
    "schema_version": 1,
    "nodes": [],
    "edges": [],
    "viewport": {"zoom": 1.0, "pan": {"x": 0.0, "y": 0.0}},
    "filters": {"hidden_labels": [], "hidden_types": []},
}


def _build_archive(
    name: str = "Test Session",
    session_id: str = "orig-id",
    findings: list | None = None,
    snapshots: dict | None = None,
    schema_version: int = 1,
) -> bytes:
    """Build a minimal .g-lab-session ZIP for use in import tests."""
    return pack_session(
        session_data={"id": session_id, "name": name, "status": "active", "config": {}},
        canvas_data=_EMPTY_CANVAS,
        findings_data=findings or [],
        action_log_ndjson="",
        snapshots=snapshots or {},
    )


def _bad_version_archive() -> bytes:
    """Build a ZIP with an unsupported future schema_version."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"{_PREFIX}/manifest.json",
            json.dumps(
                {"schema_version": 999, "exported_at": "x", "glab_version": "0.0.0"}
            ),
        )
        zf.writestr(f"{_PREFIX}/session.json", json.dumps({"name": "Bad"}))
        zf.writestr(f"{_PREFIX}/canvas.json", json.dumps(_EMPTY_CANVAS))
        zf.writestr(f"{_PREFIX}/action_log.ndjson", "")
        zf.writestr(f"{_PREFIX}/findings/index.json", "[]")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_export_returns_zip(client: AsyncClient) -> None:
    # Create a session
    r = await client.post("/api/v1/sessions", json={"name": "Export Test"})
    assert r.status_code == 201
    session_id = r.json()["data"]["id"]

    # Export it
    r = await client.post(f"/api/v1/sessions/{session_id}/export")
    assert r.status_code == 200
    assert "application/zip" in r.headers.get("content-type", "")

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read(f"{_PREFIX}/manifest.json"))

    assert f"{_PREFIX}/manifest.json" in names
    assert f"{_PREFIX}/session.json" in names
    assert f"{_PREFIX}/canvas.json" in names
    assert manifest["schema_version"] == 1
    assert manifest["session_id"] == session_id


@pytest.mark.anyio
async def test_export_includes_findings(client: AsyncClient) -> None:
    # Create session + finding
    r = await client.post("/api/v1/sessions", json={"name": "With Finding"})
    session_id = r.json()["data"]["id"]

    await client.post(
        f"/api/v1/sessions/{session_id}/findings",
        json={"title": "Important Lead", "body": "Details here"},
    )

    r = await client.post(f"/api/v1/sessions/{session_id}/export")
    assert r.status_code == 200

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        findings = json.loads(zf.read(f"{_PREFIX}/findings/index.json"))

    assert len(findings) == 1
    assert findings[0]["title"] == "Important Lead"


@pytest.mark.anyio
async def test_export_session_not_found(client: AsyncClient) -> None:
    r = await client.post("/api/v1/sessions/does-not-exist/export")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_export_content_disposition_header(client: AsyncClient) -> None:
    r = await client.post("/api/v1/sessions", json={"name": "CD Test"})
    session_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/sessions/{session_id}/export")
    assert r.status_code == 200
    disposition = r.headers.get("content-disposition", "")
    assert ".g-lab-session" in disposition
    assert session_id in disposition


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_import_creates_new_session(client: AsyncClient) -> None:
    zip_bytes = _build_archive(name="Imported", session_id="original-123")

    r = await client.post(
        "/api/v1/sessions/import",
        files={"file": ("test.g-lab-session", zip_bytes, "application/zip")},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["name"] == "Imported"
    # New UUID assigned — never the original ID
    assert data["id"] != "original-123"


@pytest.mark.anyio
async def test_import_creates_findings(client: AsyncClient) -> None:
    findings = [
        {
            "id": "f1",
            "title": "Lead A",
            "body": "Notes",
            "has_snapshot": False,
            "canvas_context": None,
        },
        {
            "id": "f2",
            "title": "Lead B",
            "body": None,
            "has_snapshot": False,
            "canvas_context": None,
        },
    ]
    zip_bytes = _build_archive(findings=findings)

    r = await client.post(
        "/api/v1/sessions/import",
        files={"file": ("test.g-lab-session", zip_bytes, "application/zip")},
    )
    assert r.status_code == 201
    session_id = r.json()["data"]["id"]

    # Verify findings were recreated
    r2 = await client.get(f"/api/v1/sessions/{session_id}/findings")
    assert r2.status_code == 200
    imported = r2.json()["data"]
    titles = {f["title"] for f in imported}
    assert titles == {"Lead A", "Lead B"}


@pytest.mark.anyio
async def test_import_bad_zip_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/sessions/import",
        files={"file": ("bad.g-lab-session", b"not a zip file", "application/zip")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_import_incompatible_version_returns_400(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/sessions/import",
        files={
            "file": ("future.g-lab-session", _bad_version_archive(), "application/zip")
        },
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_import_export_roundtrip(client: AsyncClient) -> None:
    """Full roundtrip: create → add finding → export → import → verify."""
    # Create + populate original session
    r = await client.post("/api/v1/sessions", json={"name": "Original"})
    orig_id = r.json()["data"]["id"]

    await client.post(
        f"/api/v1/sessions/{orig_id}/findings",
        json={"title": "My Finding", "body": "Important note"},
    )

    # Export
    r = await client.post(f"/api/v1/sessions/{orig_id}/export")
    assert r.status_code == 200
    zip_bytes = r.content

    # Import
    r = await client.post(
        "/api/v1/sessions/import",
        files={"file": ("round.g-lab-session", zip_bytes, "application/zip")},
    )
    assert r.status_code == 201
    new_id = r.json()["data"]["id"]
    assert new_id != orig_id

    # Findings preserved
    r2 = await client.get(f"/api/v1/sessions/{new_id}/findings")
    findings = r2.json()["data"]
    assert any(f["title"] == "My Finding" for f in findings)
