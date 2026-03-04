"""API-level tests for session and finding endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_returns_201(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/sessions", json={"name": "Test Session"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["name"] == "Test Session"
    assert body["data"]["status"] == "active"
    assert "id" in body["data"]
    assert body["data"]["canvas_state"]["nodes"] == []


@pytest.mark.asyncio
async def test_get_session_returns_200(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Get Me"})
    session_id = create.json()["data"]["id"]

    resp = await client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == session_id
    assert resp.json()["data"]["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_session_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/sessions/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_session_name(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Old Name"})
    session_id = create.json()["data"]["id"]

    resp = await client.put(f"/api/v1/sessions/{session_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Deletable"})
    session_id = create.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == session_id

    # Second delete → 404
    resp2 = await client.delete(f"/api/v1/sessions/{session_id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient) -> None:
    await client.post("/api/v1/sessions", json={"name": "Alpha"})
    await client.post("/api/v1/sessions", json={"name": "Beta"})

    resp = await client.get("/api/v1/sessions")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["data"]]
    assert "Alpha" in names
    assert "Beta" in names


# ---------------------------------------------------------------------------
# Last-active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_active_returns_none_when_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/sessions/last-active")
    assert resp.status_code == 200
    assert resp.json()["data"] is None


@pytest.mark.asyncio
async def test_last_active_returns_most_recent(client: AsyncClient) -> None:
    await client.post("/api/v1/sessions", json={"name": "First"})
    second = await client.post("/api/v1/sessions", json={"name": "Second"})
    second_id = second.json()["data"]["id"]

    resp = await client.get("/api/v1/sessions/last-active")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == second_id


# ---------------------------------------------------------------------------
# Reset — clears canvas, preserves findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_canvas_keeps_findings(client: AsyncClient) -> None:
    # Create session
    create = await client.post("/api/v1/sessions", json={"name": "Reset Me"})
    session_id = create.json()["data"]["id"]

    # Add a finding
    await client.post(
        f"/api/v1/sessions/{session_id}/findings",
        json={"title": "Important finding", "body": "Details here"},
    )

    # Update canvas state with some nodes
    from app.models.schemas import CanvasState, GraphNode

    canvas = CanvasState(
        nodes=[GraphNode(id="n1", labels=["Person"], properties={"name": "Alice"})]
    )
    await client.put(
        f"/api/v1/sessions/{session_id}",
        json={"canvas_state": canvas.model_dump()},
    )

    # Confirm canvas has nodes
    before = await client.get(f"/api/v1/sessions/{session_id}")
    assert len(before.json()["data"]["canvas_state"]["nodes"]) == 1

    # Reset
    resp = await client.post(f"/api/v1/sessions/{session_id}/reset")
    assert resp.status_code == 200
    assert resp.json()["data"]["canvas_state"]["nodes"] == []

    # Findings still exist
    findings = await client.get(f"/api/v1/sessions/{session_id}/findings")
    assert findings.status_code == 200
    assert len(findings.json()["data"]) == 1
    assert findings.json()["data"][0]["title"] == "Important finding"


@pytest.mark.asyncio
async def test_reset_not_found(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/sessions/nonexistent/reset")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export / import (smoke tests — full coverage in test_export_endpoints.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_returns_zip(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Export Me"})
    session_id = create.json()["data"]["id"]
    resp = await client.post(f"/api/v1/sessions/{session_id}/export")
    assert resp.status_code == 200
    assert "application/zip" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_import_requires_file(client: AsyncClient) -> None:
    # POST /import with no file body → 422 Unprocessable Entity
    resp = await client.post("/api/v1/sessions/import")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Findings CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_finding(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Session F"})
    session_id = create.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/sessions/{session_id}/findings",
        json={"title": "My finding", "body": "Details"},
    )
    assert resp.status_code == 201
    finding = resp.json()["data"]
    assert finding["title"] == "My finding"
    assert finding["has_snapshot"] is False

    list_resp = await client.get(f"/api/v1/sessions/{session_id}/findings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1


@pytest.mark.asyncio
async def test_update_finding(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Session G"})
    session_id = create.json()["data"]["id"]

    cf = await client.post(
        f"/api/v1/sessions/{session_id}/findings",
        json={"title": "Draft"},
    )
    finding_id = cf.json()["data"]["id"]

    resp = await client.put(
        f"/api/v1/sessions/{session_id}/findings/{finding_id}",
        json={"title": "Final Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Final Title"


@pytest.mark.asyncio
async def test_delete_finding(client: AsyncClient) -> None:
    create = await client.post("/api/v1/sessions", json={"name": "Session H"})
    session_id = create.json()["data"]["id"]

    cf = await client.post(
        f"/api/v1/sessions/{session_id}/findings",
        json={"title": "To delete"},
    )
    finding_id = cf.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/sessions/{session_id}/findings/{finding_id}")
    assert resp.status_code == 200

    list_resp = await client.get(f"/api/v1/sessions/{session_id}/findings")
    assert list_resp.json()["data"] == []
