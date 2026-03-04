"""API-level tests for graph endpoints (mocked Neo4jService)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_neo4j
from app.routers import graph as graph_router
from app.services.neo4j_service import Neo4jService
from app.utils.exceptions import CypherValidationError

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

_NODE = {"id": "4:abc:1", "labels": ["Person"], "properties": {"name": "Alice"}}
_EDGE = {
    "id": "4:abc:10",
    "type": "KNOWS",
    "source": "4:abc:1",
    "target": "4:abc:2",
    "properties": {},
}
_SCHEMA = {
    "labels": [{"name": "Person", "count": 10, "property_keys": ["name"]}],
    "relationship_types": [{"name": "KNOWS", "count": 5, "property_keys": []}],
}


def _make_mock_neo4j() -> MagicMock:
    """Build a Neo4jService mock with sensible defaults."""
    mock = MagicMock(spec=Neo4jService)
    mock.get_schema = AsyncMock(return_value=_SCHEMA)
    mock.get_samples = AsyncMock(return_value=[_NODE])
    mock.get_relationship_samples = AsyncMock(return_value=[_EDGE])
    mock.search = AsyncMock(return_value=[_NODE])
    mock.expand = AsyncMock(return_value=([_NODE], [_EDGE]))
    mock.find_paths = AsyncMock(return_value=([], [], []))
    mock.execute_raw = AsyncMock(return_value=[{"n": {"name": "Alice"}}])
    return mock


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def graph_client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    """Async test client wired to a minimal app with mocked Neo4jService."""
    mock_neo4j = _make_mock_neo4j()

    def override_get_neo4j(_request: Request) -> Neo4jService:
        return mock_neo4j  # type: ignore[return-value]

    test_app = FastAPI()
    test_app.include_router(graph_router.router, prefix="/api/v1/graph")
    test_app.dependency_overrides[get_neo4j] = override_get_neo4j

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as c:
        yield c, mock_neo4j


# ---------------------------------------------------------------------------
# GET /graph/schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_returns_labels_and_types(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, _ = graph_client
    resp = await client.get("/api/v1/graph/schema")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["labels"][0]["name"] == "Person"
    assert data["relationship_types"][0]["name"] == "KNOWS"


# ---------------------------------------------------------------------------
# GET /graph/schema/samples/{label}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_label_samples_returns_nodes(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    resp = await client.get("/api/v1/graph/schema/samples/Person")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert data[0]["labels"] == ["Person"]
    mock.get_samples.assert_called_once_with("Person")


# ---------------------------------------------------------------------------
# GET /graph/schema/samples/rel/{rel_type}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rel_samples_returns_edges(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    resp = await client.get("/api/v1/graph/schema/samples/rel/KNOWS")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    mock.get_relationship_samples.assert_called_once_with("KNOWS")


# ---------------------------------------------------------------------------
# POST /graph/search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_envelope(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, _ = graph_client
    resp = await client.post(
        "/api/v1/graph/search",
        json={"query": "Alice", "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "warnings" in body
    assert "meta" in body
    nodes = body["data"]["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == "4:abc:1"


@pytest.mark.asyncio
async def test_search_passes_labels_filter(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    await client.post(
        "/api/v1/graph/search",
        json={"query": "Corp", "labels": ["Company"], "limit": 5},
    )
    mock.search.assert_called_once_with(
        query="Corp", labels=["Company"], limit=5
    )


# ---------------------------------------------------------------------------
# POST /graph/expand — guardrail rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_at_capacity_returns_409(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    """490 nodes on canvas + requesting 20 → remaining=10 < 20 → 409."""
    client, mock = graph_client
    resp = await client.post(
        "/api/v1/graph/expand",
        json={
            "node_ids": ["4:abc:1"],
            "hops": 1,
            "limit": 20,
            "current_canvas_count": 490,
        },
    )
    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["code"] == "GUARDRAIL_EXCEEDED"
    detail = error["detail"]
    assert detail["requested"] == 20
    assert detail["remaining"] == 10
    assert detail["hard_limit"] == 500
    assert detail["current"] == 490
    # Neo4j should NOT have been called
    mock.expand.assert_not_called()


# ---------------------------------------------------------------------------
# POST /graph/expand — successful expansion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_with_room_returns_200(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    """480 nodes on canvas + requesting 20 → remaining=20 == 20 → 200."""
    client, _ = graph_client
    resp = await client.post(
        "/api/v1/graph/expand",
        json={
            "node_ids": ["4:abc:1"],
            "hops": 1,
            "limit": 20,
            "current_canvas_count": 480,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["nodes"]) == 1
    assert len(data["edges"]) == 1


@pytest.mark.asyncio
async def test_expand_hops_passed_to_service(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    """Requested hops=3 should be passed through to neo4j.expand."""
    client, mock = graph_client
    resp = await client.post(
        "/api/v1/graph/expand",
        json={
            "node_ids": ["4:abc:1"],
            "hops": 3,
            "limit": 10,
            "current_canvas_count": 0,
        },
    )
    assert resp.status_code == 200
    call_kwargs = mock.expand.call_args.kwargs
    assert call_kwargs["hops"] == 3


@pytest.mark.asyncio
async def test_expand_warning_when_canvas_near_limit(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    """Canvas at 410 (≥ 400 threshold) → allowed but warning returned."""
    client, _ = graph_client
    resp = await client.post(
        "/api/v1/graph/expand",
        json={
            "node_ids": ["4:abc:1"],
            "hops": 1,
            "limit": 10,
            "current_canvas_count": 410,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["warnings"]) > 0


# ---------------------------------------------------------------------------
# POST /graph/paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paths_returns_200(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    # Return a dedup-node result
    mock.find_paths = AsyncMock(return_value=([[]], [_NODE], []))
    resp = await client.post(
        "/api/v1/graph/paths",
        json={
            "source_id": "4:abc:1",
            "target_id": "4:abc:2",
            "max_hops": 3,
            "mode": "shortest",
            "current_canvas_count": 0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "paths" in data
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 1


@pytest.mark.asyncio
async def test_paths_hops_passed_to_service(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    await client.post(
        "/api/v1/graph/paths",
        json={
            "source_id": "4:abc:1",
            "target_id": "4:abc:2",
            "max_hops": 4,
            "mode": "all_shortest",
            "current_canvas_count": 0,
        },
    )
    mock.find_paths.assert_called_once_with(
        source_id="4:abc:1",
        target_id="4:abc:2",
        max_hops=4,
        mode="all_shortest",
    )


# ---------------------------------------------------------------------------
# POST /graph/query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raw_query_valid_returns_200(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, _ = graph_client
    resp = await client.post(
        "/api/v1/graph/query",
        json={"query": "MATCH (n) RETURN n LIMIT 5"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "results" in data


@pytest.mark.asyncio
async def test_raw_query_write_raises_400(
    graph_client: tuple[AsyncClient, MagicMock],
) -> None:
    client, mock = graph_client
    mock.execute_raw = AsyncMock(
        side_effect=CypherValidationError("Write operations are not allowed")
    )
    resp = await client.post(
        "/api/v1/graph/query",
        json={"query": "CREATE (n:Person {name: 'Bob'}) RETURN n"},
    )
    assert resp.status_code == 400
    assert "Write operations" in resp.json()["detail"]
