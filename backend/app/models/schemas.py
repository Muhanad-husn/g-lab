"""Pydantic request/response schemas.

All schemas follow the canonical type contracts defined in ARCHITECTURE.md §14.
Graph data types (§14.2) and request/response schemas (§14.3) live here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Graph data types (§14.2)
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]
    position: dict[str, float] | None = None


class GraphEdge(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any]


class CanvasViewport(BaseModel):
    zoom: float = 1.0
    pan: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class CanvasFilters(BaseModel):
    hidden_labels: list[str] = Field(default_factory=list)
    hidden_types: list[str] = Field(default_factory=list)


class CanvasState(BaseModel):
    schema_version: int = 1
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    viewport: CanvasViewport = Field(default_factory=CanvasViewport)
    filters: CanvasFilters = Field(default_factory=CanvasFilters)


# ---------------------------------------------------------------------------
# Schema / database overview types (§14.3)
# ---------------------------------------------------------------------------


class LabelInfo(BaseModel):
    name: str
    count: int | None  # None if count query timed out
    property_keys: list[str]


class RelTypeInfo(BaseModel):
    name: str
    count: int | None
    property_keys: list[str]


class SchemaResponse(BaseModel):
    labels: list[LabelInfo]
    relationship_types: list[RelTypeInfo]


# ---------------------------------------------------------------------------
# Graph query request/response schemas (§14.3)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    labels: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    nodes: list[GraphNode]


class ExpandRequest(BaseModel):
    node_ids: list[str]
    relationship_types: list[str] | None = None
    hops: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=25, ge=1, le=100)
    current_canvas_count: int


class ExpandResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PathRequest(BaseModel):
    source_id: str
    target_id: str
    max_hops: int = Field(default=5, ge=1, le=5)
    mode: Literal["shortest", "all_shortest"] = "shortest"
    current_canvas_count: int


class PathResponse(BaseModel):
    paths: list[list[GraphNode | GraphEdge]]
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RawQueryRequest(BaseModel):
    query: str
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session schemas (§14.3)
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    name: str


class SessionUpdate(BaseModel):
    name: str | None = None
    canvas_state: CanvasState | None = None
    config: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    status: str
    canvas_state: CanvasState
    config: dict[str, Any]


# ---------------------------------------------------------------------------
# Finding schemas (§14.3)
# ---------------------------------------------------------------------------


class FindingCreate(BaseModel):
    title: str
    body: str | None = None
    snapshot_png: str | None = None  # base64-encoded
    canvas_context: list[str] | None = None  # node/edge IDs visible at save time


class FindingUpdate(BaseModel):
    title: str | None = None
    body: str | None = None


class FindingResponse(BaseModel):
    id: str
    session_id: str
    created_at: str
    updated_at: str
    title: str
    body: str | None
    has_snapshot: bool
    canvas_context: list[str] | None
