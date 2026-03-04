// ─── API Envelope ────────────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.1

export interface ApiResponse<T> {
  data: T;
  warnings: string[];
  meta: {
    request_id: string;
    duration_ms: number;
  };
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    detail?: Record<string, unknown>;
  };
  meta: { request_id: string };
}

// ─── Graph Data Types ────────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.2

export interface GraphNode {
  id: string; // Neo4j element ID (string like "4:abc:123")
  labels: string[];
  properties: Record<string, unknown>;
  position?: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  type: string;
  source: string; // node ID
  target: string; // node ID
  properties: Record<string, unknown>;
}

export interface CanvasState {
  schema_version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  viewport: { zoom: number; pan: { x: number; y: number } };
  filters: {
    hidden_labels: string[];
    hidden_types: string[];
  };
}

// ─── Session & Findings ──────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.3

export interface SessionResponse {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  status: string;
  canvas_state: CanvasState;
  config: Record<string, unknown>;
}

export interface SessionCreate {
  name: string;
}

export interface SessionUpdate {
  name?: string | null;
  canvas_state?: CanvasState | null;
  config?: Record<string, unknown> | null;
}

export interface FindingResponse {
  id: string;
  session_id: string;
  created_at: string;
  updated_at: string;
  title: string;
  body: string | null;
  has_snapshot: boolean;
  canvas_context: string[] | null;
}

export interface FindingCreate {
  title: string;
  body?: string | null;
  snapshot_png?: string | null;
  canvas_context?: string[] | null;
}

export interface FindingUpdate {
  title?: string;
  body?: string | null;
}

// ─── Graph Requests / Responses ──────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.3

export interface SearchRequest {
  query: string;
  labels?: string[] | null;
  limit?: number;
}

export interface SearchResponse {
  nodes: GraphNode[];
}

export interface ExpandRequest {
  node_ids: string[];
  relationship_types?: string[] | null;
  hops?: number;
  limit?: number;
  current_canvas_count: number;
}

export interface ExpandResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface PathRequest {
  source_id: string;
  target_id: string;
  max_hops?: number;
  mode?: "shortest" | "all_shortest";
  current_canvas_count: number;
}

export interface PathResponse {
  paths: (GraphNode | GraphEdge)[][];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── Schema ──────────────────────────────────────────────────────────────────

export interface LabelInfo {
  name: string;
  count: number | null;
  property_keys: string[];
}

export interface RelTypeInfo {
  name: string;
  count: number | null;
  property_keys: string[];
}

export interface SchemaResponse {
  labels: LabelInfo[];
  relationship_types: RelTypeInfo[];
}

export interface RawQueryRequest {
  cypher: string;
  params?: Record<string, unknown>;
}

// ─── Guardrail detail (in ApiError.error.detail) ─────────────────────────────

export interface GuardrailDetail {
  requested: number;
  remaining: number;
  hard_limit: number;
  current: number;
}
