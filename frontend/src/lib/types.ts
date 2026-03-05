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
    collapsed_labels?: string[];
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
  session_id?: string | null;
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
  session_id?: string | null;
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
  session_id?: string | null;
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

// ─── Phase 2: Presets ─────────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.3 / backend PresetConfig

export interface PresetConfig {
  hops: number;
  expansionLimit: number;
  docTopK: number;
  docRerankerK: number;
  models: {
    router: string;
    graphRetrieval: string;
    synthesiser: string;
  };
  tokenBudgets: {
    router: number;
    graphRetrieval: number;
    synthesiser: number;
  };
  advancedMode: boolean;
}

export interface PresetCreate {
  name: string;
  config: PresetConfig;
}

export interface PresetUpdate {
  name?: string | null;
  config?: PresetConfig | null;
}

export interface PresetResponse {
  id: string;
  name: string;
  is_system: boolean;
  config: PresetConfig;
}

// ─── Phase 2: Copilot ─────────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14.3 / backend copilot schemas

export interface CopilotQueryRequest {
  query: string;
  session_id: string;
  include_graph_context?: boolean;
}

export interface CopilotMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown> | null;
}

export interface RouterIntent {
  needs_graph: boolean;
  needs_docs: boolean;
  cypher_hint: string | null;
  doc_query: string | null;
}

export interface ConfidenceScore {
  score: number; // 0.0–1.0
  band: "high" | "medium" | "low";
}

export interface GraphDelta {
  add_nodes: GraphNode[];
  add_edges: GraphEdge[];
}

export interface EvidenceSource {
  type: "graph_path" | "doc_chunk";
  id: string;
  content: string;
  // Optional metadata for doc_chunk type
  filename?: string;
  page_number?: number | null;
  section_heading?: string | null;
  parse_tier?: ParseTier;
}

// ─── Phase 2: SSE Events ──────────────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §5.5

export interface SSETextChunkEvent {
  type: "text_chunk";
  data: { content: string };
}

export interface SSEEvidenceEvent {
  type: "evidence";
  data: { sources: EvidenceSource[] };
}

export interface SSEGraphDeltaEvent {
  type: "graph_delta";
  data: GraphDelta;
}

export interface SSEConfidenceEvent {
  type: "confidence";
  data: ConfidenceScore;
}

export interface SSEStatusEvent {
  type: "status";
  data: { stage: string };
}

export interface SSEDoneEvent {
  type: "done";
  data: Record<string, never>;
}

export interface SSEErrorEvent {
  type: "error";
  data: { code: string; message: string };
}

export type SSEEvent =
  | SSETextChunkEvent
  | SSEEvidenceEvent
  | SSEGraphDeltaEvent
  | SSEConfidenceEvent
  | SSEStatusEvent
  | SSEDoneEvent
  | SSEErrorEvent;

// ─── Phase 2: OpenRouter Models ───────────────────────────────────────────────

export interface ModelInfo {
  id: string;
  name: string;
  context_length?: number;
  pricing?: { prompt: string; completion: string };
}

// ─── Phase 3: Document Libraries ──────────────────────────────────────────────
// Source of truth: docs/ARCHITECTURE.md §14 / backend DocumentLibraryResponse

export type ParseTier = "high" | "standard" | "basic" | "pending";

export interface DocumentLibrary {
  id: string;
  name: string;
  created_at: string;
  doc_count: number;
  chunk_count: number;
  parse_quality: ParseTier | null;
  indexed_at: string | null;
}

export interface DocumentInfo {
  id: string;
  library_id: string;
  filename: string;
  file_hash: string;
  parse_tier: ParseTier;
  chunk_count: number;
  uploaded_at: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  parse_tier: ParseTier;
  chunk_count: number;
}

export interface ChunkMetadata {
  document_id: string;
  library_id: string;
  page_number: number | null;
  section_heading: string | null;
  chunk_index: number;
  parse_tier: ParseTier;
}

export interface DocumentChunk {
  id: string;
  text: string;
  metadata: ChunkMetadata;
  similarity_score?: number;
}

export interface LibraryAttachRequest {
  session_id: string;
}
