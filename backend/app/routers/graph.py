"""Graph query endpoints.

All endpoints are prefixed with /api/v1/graph (set in main.py).

Pattern: validate → guardrail pre-check → service call → envelope.

HTTP status codes:
  400 — Cypher sanitiser rejection
  409 — Guardrail hard limit exceeded
  503 — Neo4j unavailable (raised by get_neo4j dependency)
  504 — Query timeout

IMPORTANT: GET /schema/samples/rel/{rel_type} is defined BEFORE
GET /schema/samples/{label} so FastAPI does not swallow "rel" as
a label name on the 4-segment path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.dependencies import get_action_logger, get_neo4j
from app.models.enums import ActionType
from app.models.schemas import (
    ExpandRequest,
    ExpandResponse,
    GraphEdge,
    GraphNode,
    PathRequest,
    PathResponse,
    RawQueryRequest,
    SchemaResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.action_log import ActionLogger
from app.services.guardrails import GuardrailService
from app.services.neo4j_service import Neo4jService
from app.utils.exceptions import CypherValidationError
from app.utils.response import envelope, error_response

router = APIRouter()
_guardrails = GuardrailService()


# ---------------------------------------------------------------------------
# GET /graph/schema
# ---------------------------------------------------------------------------


@router.get("/schema")
async def get_schema(
    neo4j: Neo4jService = Depends(get_neo4j),
) -> dict[str, Any]:
    try:
        schema_data = await neo4j.get_schema()
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Schema query timed out") from exc
    return envelope(SchemaResponse(**schema_data).model_dump())


# ---------------------------------------------------------------------------
# GET /graph/schema/samples/rel/{rel_type}  (defined BEFORE /{label})
# ---------------------------------------------------------------------------


@router.get("/schema/samples/rel/{rel_type}")
async def get_rel_samples(
    rel_type: str,
    neo4j: Neo4jService = Depends(get_neo4j),
) -> dict[str, Any]:
    try:
        samples = await neo4j.get_relationship_samples(rel_type)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Sample query timed out") from exc
    return envelope(samples)


# ---------------------------------------------------------------------------
# GET /graph/schema/samples/{label}
# ---------------------------------------------------------------------------


@router.get("/schema/samples/{label}")
async def get_label_samples(
    label: str,
    neo4j: Neo4jService = Depends(get_neo4j),
) -> dict[str, Any]:
    try:
        samples = await neo4j.get_samples(label)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Sample query timed out") from exc
    nodes = [GraphNode(**n) for n in samples]
    return envelope([n.model_dump() for n in nodes])


# ---------------------------------------------------------------------------
# POST /graph/search
# ---------------------------------------------------------------------------


@router.post("/search")
async def search_nodes(
    body: SearchRequest,
    background_tasks: BackgroundTasks,
    neo4j: Neo4jService = Depends(get_neo4j),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    try:
        raw_nodes = await neo4j.search(
            query=body.query,
            labels=body.labels,
            limit=body.limit,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Search query timed out") from exc
    nodes = [GraphNode(**n) for n in raw_nodes]
    if body.session_id:
        background_tasks.add_task(
            action_logger.log,
            session_id=body.session_id,
            action_type=ActionType.NODE_SEARCH,
            actor="user",
            payload={"query": body.query, "labels": body.labels},
            result_summary={"result_count": len(nodes)},
        )
    return envelope(SearchResponse(nodes=nodes).model_dump())


# ---------------------------------------------------------------------------
# POST /graph/expand
# ---------------------------------------------------------------------------


@router.post("/expand")
async def expand_nodes(
    body: ExpandRequest,
    background_tasks: BackgroundTasks,
    neo4j: Neo4jService = Depends(get_neo4j),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> Any:
    # Guardrail pre-check: canvas capacity
    expansion_result = _guardrails.check_expansion(
        current_count=body.current_canvas_count,
        requested_limit=body.limit,
    )
    if not expansion_result.allowed:
        return JSONResponse(
            status_code=409,
            content=error_response(
                code="GUARDRAIL_EXCEEDED",
                message="Canvas node limit would be exceeded",
                detail=expansion_result.detail,
            ),
        )

    # Guardrail pre-check: hop count
    hops_result = _guardrails.check_hops(requested=body.hops)
    effective_hops = (
        hops_result.detail["effective_hops"] if hops_result.detail else body.hops
    )

    warnings = expansion_result.warnings + hops_result.warnings

    try:
        raw_nodes, raw_edges = await neo4j.expand(
            node_ids=body.node_ids,
            rel_types=body.relationship_types,
            hops=effective_hops,
            limit=body.limit,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Expand query timed out") from exc

    nodes = [GraphNode(**n) for n in raw_nodes]
    edges = [GraphEdge(**e) for e in raw_edges]
    if body.session_id:
        background_tasks.add_task(
            action_logger.log,
            session_id=body.session_id,
            action_type=ActionType.NODE_EXPAND,
            actor="user",
            payload={"node_ids": body.node_ids, "hops": effective_hops},
            result_summary={"node_count": len(nodes), "edge_count": len(edges)},
            guardrail_warnings=warnings if warnings else None,
        )
    return envelope(
        ExpandResponse(nodes=nodes, edges=edges).model_dump(),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# POST /graph/paths
# ---------------------------------------------------------------------------


@router.post("/paths")
async def find_paths(
    body: PathRequest,
    background_tasks: BackgroundTasks,
    neo4j: Neo4jService = Depends(get_neo4j),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    # Guardrail pre-check: hop count
    hops_result = _guardrails.check_hops(requested=body.max_hops)
    effective_hops = (
        hops_result.detail["effective_hops"] if hops_result.detail else body.max_hops
    )

    try:
        raw_paths, raw_nodes, raw_edges = await neo4j.find_paths(
            source_id=body.source_id,
            target_id=body.target_id,
            max_hops=effective_hops,
            mode=body.mode,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Path query timed out") from exc

    nodes = [GraphNode(**n) for n in raw_nodes]
    edges = [GraphEdge(**e) for e in raw_edges]
    if body.session_id:
        background_tasks.add_task(
            action_logger.log,
            session_id=body.session_id,
            action_type=ActionType.PATH_DISCOVERY,
            actor="user",
            payload={
                "source_id": body.source_id,
                "target_id": body.target_id,
                "max_hops": effective_hops,
                "mode": body.mode,
            },
            result_summary={"path_count": len(raw_paths), "node_count": len(nodes)},
            guardrail_warnings=hops_result.warnings if hops_result.warnings else None,
        )
    return envelope(
        PathResponse(
            paths=raw_paths,
            nodes=nodes,
            edges=edges,
        ).model_dump(),
        warnings=hops_result.warnings,
    )


# ---------------------------------------------------------------------------
# POST /graph/query
# ---------------------------------------------------------------------------


@router.post("/query")
async def raw_query(
    body: RawQueryRequest,
    background_tasks: BackgroundTasks,
    neo4j: Neo4jService = Depends(get_neo4j),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    try:
        results = await neo4j.execute_raw(cypher=body.query)
    except CypherValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Query timed out") from exc
    if body.session_id:
        background_tasks.add_task(
            action_logger.log,
            session_id=body.session_id,
            action_type=ActionType.RAW_QUERY,
            actor="user",
            payload={"query": body.query},
            result_summary={"row_count": len(results)},
        )
    return envelope({"results": results})
