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


class CentralNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]
    degree: int


class GraphOverview(BaseModel):
    schema_info: SchemaResponse
    central_nodes: list[CentralNode]


# ---------------------------------------------------------------------------
# Graph query request/response schemas (§14.3)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    labels: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    session_id: str | None = None


class SearchResponse(BaseModel):
    nodes: list[GraphNode]


class ExpandRequest(BaseModel):
    node_ids: list[str]
    relationship_types: list[str] | None = None
    hops: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=25, ge=1, le=100)
    current_canvas_count: int
    session_id: str | None = None


class ExpandResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PathRequest(BaseModel):
    source_id: str
    target_id: str
    max_hops: int = Field(default=5, ge=1, le=5)
    mode: Literal["shortest", "all_shortest"] = "shortest"
    current_canvas_count: int
    session_id: str | None = None


class PathResponse(BaseModel):
    paths: list[list[GraphNode | GraphEdge]]
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RawQueryRequest(BaseModel):
    query: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


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


# ---------------------------------------------------------------------------
# Preset schemas (Phase 2 — §14.3)
# ---------------------------------------------------------------------------


class PresetConfig(BaseModel):
    hops: int = 2
    expansionLimit: int = 25
    docTopK: int = 5
    docRerankerK: int = 3
    models: dict[str, str] = Field(
        default_factory=lambda: {
            "router": "anthropic/claude-3-haiku-20240307",
            "graphRetrieval": "anthropic/claude-3-5-sonnet-20241022",
            "synthesiser": "anthropic/claude-3.5-sonnet",
        }
    )
    tokenBudgets: dict[str, int] = Field(
        default_factory=lambda: {
            "router": 256,
            "graphRetrieval": 512,
            "synthesiser": 4096,
        }
    )
    advancedMode: bool = False


class PresetCreate(BaseModel):
    name: str
    config: PresetConfig


class PresetUpdate(BaseModel):
    name: str | None = None
    config: PresetConfig | None = None


class PresetResponse(BaseModel):
    id: str
    name: str
    is_system: bool
    config: PresetConfig


# ---------------------------------------------------------------------------
# Copilot schemas (Phase 2 — §14.3)
# ---------------------------------------------------------------------------


class CopilotQueryRequest(BaseModel):
    query: str
    session_id: str
    include_graph_context: bool = True
    model_assignments: dict[str, str] | None = None


class CopilotMessage(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str
    metadata: dict[str, Any] | None = None


class RouterIntent(BaseModel):
    needs_graph: bool = True
    needs_docs: bool = False
    cypher_hint: str | None = None
    doc_query: str | None = None


class ConfidenceScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    band: Literal["high", "medium", "low"]


class GraphDelta(BaseModel):
    add_nodes: list[GraphNode] = Field(default_factory=list)
    add_edges: list[GraphEdge] = Field(default_factory=list)


class EvidenceSource(BaseModel):
    type: Literal["graph_path", "doc_chunk"]
    id: str
    content: str
    # Optional metadata for doc_chunk type
    filename: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    parse_tier: str | None = None


# ---------------------------------------------------------------------------
# Document Library schemas (Phase 3 — §14.3)
# ---------------------------------------------------------------------------


class DocumentLibraryCreate(BaseModel):
    name: str


class DocumentLibraryResponse(BaseModel):
    id: str
    name: str
    created_at: str
    doc_count: int
    chunk_count: int
    parse_quality: str | None
    indexed_at: str | None


class DocumentResponse(BaseModel):
    id: str
    library_id: str
    filename: str
    file_hash: str
    parse_tier: str
    chunk_count: int
    uploaded_at: str


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    parse_tier: str
    chunk_count: int


class LibraryAttachRequest(BaseModel):
    session_id: str


class ChunkMetadata(BaseModel):
    document_id: str
    library_id: str
    page_number: int | None = None
    section_heading: str | None = None
    chunk_index: int
    parse_tier: str


class DocumentChunk(BaseModel):
    id: str
    text: str
    metadata: ChunkMetadata
    similarity_score: float | None = None


class DocumentRetrievalResult(BaseModel):
    chunks: list[DocumentChunk]
    evidence_sources: list[EvidenceSource]


# ---------------------------------------------------------------------------
# Credentials schemas (runtime connection settings)
# ---------------------------------------------------------------------------


class CredentialsUpdate(BaseModel):
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None
    openrouter_api_key: str | None = None


class CredentialsStatus(BaseModel):
    neo4j_uri: str
    neo4j_user: str
    neo4j_password_set: bool
    openrouter_api_key_set: bool
    neo4j_connected: bool
    openrouter_configured: bool
