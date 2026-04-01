G-Lab — ARCHITECTURE.md
========================

> **Status:** v3.1 — March 2026
> **Ownership:** This document defines _how_ G-Lab is built. `PRODUCT.md` defines _what_ it is and _why_. `CLAUDE.md` files define coding conventions and gotchas per directory. `STRUCTURE_PH1.md` defines the build order. No product rationale lives here; no schema or wire format lives there.

* * *

## 1. System Overview

G-Lab is a self-hosted, single-user application deployed via Docker Compose. All components run on the investigator's own machine. Nothing leaves the host.

```
┌─────────────────────────────────────────────────────────────┐
│  Host Machine (Docker Compose)                              │
│                                                             │
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────┐  │
│  │  Frontend    │────▶│  Backend API │────▶│  Neo4j      │  │
│  │  (React SPA) │◀────│  (FastAPI)   │◀────│  (user-     │  │
│  │  :5173       │     │  :8000       │     │  managed)   │  │
│  └─────────────┘     └──────┬───────┘     └─────────────┘  │
│                             │                               │
│                     ┌───────┴────────┐                      │
│                     │                │                      │
│               ┌─────▼─────┐   ┌─────▼──────┐               │
│               │  SQLite    │   │  ChromaDB   │  ← Phase 3   │
│               │  (sessions,│   │  (vectors)  │              │
│               │   logs)    │   │  :8100      │              │
│               └───────────┘   └────────────┘               │
│                     │                                       │
│                     │ (outbound, Phases 2–3 only)           │
│                     ▼                                       │
│              ┌─────────────┐                                │
│              │  OpenRouter  │                                │
│              │  (LLM proxy) │                                │
│              └─────────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

**Component summary:**

| Component   | Technology         | Phase | Role                                                       |
| ----------- | ------------------ | ----- | ---------------------------------------------------------- |
| Frontend    | React + TypeScript | 1     | Canvas, Navigator, Inspector, Copilot panel, all UI        |
| Backend API | FastAPI (Python)   | 1     | Session management, Neo4j proxy, guardrail enforcement     |
| Neo4j       | User-managed       | 1     | Graph database — G-Lab connects read-only                  |
| SQLite      | Embedded           | 1     | Session state, action log, durable findings                |
| OpenRouter  | External SaaS      | 2     | LLM gateway for Router, Graph Retrieval, Synthesiser roles |
| ChromaDB    | Self-hosted        | 3     | Vector store for document embeddings                       |

**Key constraint:** Neo4j is _not_ managed by G-Lab. The user provides connection credentials. G-Lab connects read-only and never writes to the graph.

* * *

## 2. Technology Choices

### 2.1 Frontend — React + TypeScript

**Canvas renderer:** Cytoscape.js. Chosen over D3 (too low-level for interactive graph manipulation) and Sigma.js (weaker layout ecosystem). Cytoscape provides built-in and extension-based layout algorithms — CoSE-Bilkent (force-directed, default), Concentric, Grid, AVSDF (circular), CiSE, Cola, Euler, Spread, Dagre (hierarchical), and Klay (hierarchical) — compound nodes for future grouping, and a well-documented extension API. Rendering target is Canvas 2D via `cytoscape-canvas`; WebGL (via `cytoscape-webgl`) is a future optimisation if the 500-node cap proves insufficient before layout degrades.

**State management:** Zustand. The application state decomposes into a few distinct slices (graph, session, UI, copilot) with moderate cross-slice reads but rare cross-slice writes. Zustand's lightweight footprint and selector-based subscriptions avoid unnecessary re-renders on canvas-heavy updates. Redux is overkill here; signals-based solutions are too immature for the ecosystem tooling we need.

**Layout & styling:** Tailwind CSS with a constrained design token set. Component library: shadcn/ui for non-canvas UI (panels, dialogs, forms, toasts). The canvas itself is entirely Cytoscape-rendered — no HTML overlay nodes.

**Streaming:** The Copilot panel consumes SSE via the native `EventSource` API, with a thin wrapper for retry and structured message parsing.

**Build tooling:** Vite. Fast HMR, native ESM, minimal config.

### 2.2 Backend — FastAPI (Python)

Python is the natural choice: the AI pipeline (Phase 2), document ingestion (Phase 3), and Neo4j driver (`neo4j` Python SDK) all have first-class Python support. FastAPI provides async request handling, automatic OpenAPI docs, and Pydantic models for request/response validation.

**ASGI server:** Uvicorn with a single worker. G-Lab is single-user; concurrency needs are modest. The main concurrency concern is streaming a Copilot response while the user makes synchronous graph queries — async handles this cleanly.

**Neo4j driver:** Official `neo4j` Python driver in read-only mode. Every Cypher query is executed inside a read transaction. The driver's connection pool defaults (max 100 connections) are far above what a single-user app needs; pool size is capped at 10.

### 2.3 Session Storage — SQLite

SQLite is the persistence layer for everything except graph data and document vectors. It runs embedded in the backend process — no separate container, no network hop.

**Why not Postgres?** G-Lab is single-user and single-process. SQLite's single-writer model is a feature here, not a limitation. It eliminates an entire container and operational surface. File-level backup and portability align with the export/reproducibility design principle.

**WAL mode** is enabled for read concurrency during long writes (e.g., bulk action log inserts during session export).

### 2.4 Vector Store — ChromaDB (Phase 3)

ChromaDB is chosen for document embedding storage. It runs as a sidecar container with persistent volume. Selection rationale: embeds the embedding model locally (no external API call for indexing), has a simple Python client, and supports metadata filtering on chunks.

**Embedding model:** `all-MiniLM-L6-v2` (384 dimensions) as the default. Configured via environment variable to allow swapping without code changes. The model runs inside ChromaDB's container.

### 2.5 LLM Access — OpenRouter (Phase 2)

All LLM calls route through OpenRouter. G-Lab never calls model providers directly.

**Rationale:** OpenRouter provides a single API surface across providers, handles auth, and lets the user choose models without G-Lab needing per-provider integration. The user provides their own OpenRouter API key — G-Lab stores it encrypted at rest (see Section 6).

* * *

## 3. Backend Architecture

### 3.1 Module Structure

```
backend/
├── main.py                     # FastAPI app, lifespan, middleware
├── config.py                   # Settings (env vars, defaults)
├── dependencies.py             # FastAPI dependency injection
│
├── routers/
│   ├── graph.py                # Neo4j query endpoints
│   ├── sessions.py             # Session CRUD, export/import
│   ├── findings.py             # Durable findings CRUD
│   ├── copilot.py              # Copilot query + SSE streaming  (Phase 2)
│   ├── documents.py            # Document library management    (Phase 3)
│   └── config_presets.py       # Preset CRUD                   (Phase 2)
│
├── services/
│   ├── neo4j_service.py        # Neo4j driver, schema introspection, query execution
│   ├── session_service.py      # Session lifecycle logic
│   ├── guardrails.py           # Limit enforcement (hard + soft)
│   ├── action_log.py           # Event logging to NDJSON + SQLite
│   ├── copilot/                # (Phase 2)
│   │   ├── router.py           # Intent classification
│   │   ├── graph_retrieval.py  # Cypher generation + execution
│   │   ├── synthesiser.py      # Answer composition + confidence scoring
│   │   └── openrouter.py       # OpenRouter HTTP client
│   └── documents/              # (Phase 3)
│       ├── ingestion.py        # Parse pipeline (Docling → Unstructured → raw)
│       ├── chunking.py         # Recursive text splitting
│       └── retrieval.py        # Vector search + reranking
│
├── models/
│   ├── schemas.py              # Pydantic request/response models
│   ├── db.py                   # SQLAlchemy/SQLite models + session factory
│   └── enums.py                # Shared enumerations
│
└── utils/
    ├── cypher.py               # Cypher query builder + sanitiser
    ├── export.py               # Session archive packing/unpacking
    └── crypto.py               # API key encryption helpers
```

### 3.2 Request Lifecycle

A typical graph query flows through:

```
HTTP request
  → FastAPI router (path matching, auth — future)
    → Pydantic model validation
      → Guardrail check (guardrails.py)
        → Service layer (neo4j_service.py)
          → Neo4j driver (read transaction)
        ← Result mapping to response schema
      ← Guardrail annotation (warnings if near limits)
    ← Pydantic response serialization
  ← HTTP response (JSON)
```

Guardrails are enforced _before_ the query executes, not after. If an expansion would exceed the canvas node cap, the request is rejected with a `409 Conflict` containing the current count, the requested count, and the remaining capacity. The frontend uses this to render the appropriate banner.

### 3.3 Neo4j Interaction

**All queries are read-only.** The Neo4j driver is configured with `default_access_mode=READ`. As a defence-in-depth measure, the backend's Cypher sanitiser rejects any query containing write clauses (`CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `CALL {...}`). This is a static check on the query string before execution, not a runtime interceptor.

**Schema introspection** (for the Database Overview) uses Neo4j's built-in procedures:

| Data needed             | Procedure / query                                           |
| ----------------------- | ----------------------------------------------------------- |
| Node labels             | `CALL db.labels()`                                          |
| Relationship types      | `CALL db.relationshipTypes()`                               |
| Property keys per label | `CALL db.schema.nodeTypeProperties()`                       |
| Counts per label        | `MATCH (n:Label) RETURN count(n)` (one query per label)     |
| Sample nodes            | `MATCH (n:Label) RETURN n LIMIT 5` (per label)              |
| Sample relationships    | `MATCH (a)-[r:TYPE]->(b) RETURN a, r, b LIMIT 5` (per type) |

Count queries use a 10-second timeout (separate from the general 30-second hard limit) since they may be slow on large databases. If a count query times out, the UI shows "—" instead of a number.

**Cypher timeout enforcement:** Every query is wrapped with `CALL dbms.setConfigValue('db.transaction.timeout', '30s')` — no, this is impractical for per-query control. Instead, the Python driver's `session.run()` is given a `timeout` parameter (in milliseconds). The driver aborts the transaction server-side if the timeout fires.

**Path discovery:**

- Shortest path: `shortestPath((a)-[*..{maxHops}]-(b))` with the hop limit drawn from the active preset (soft limit, max 5).
- All paths (bounded): `allShortestPaths((a)-[*..{maxHops}]-(b))`. This is intentionally `allShortestPaths`, not unbounded `allPaths`, to prevent combinatorial explosion.

### 3.4 Action Logging

Every user and system action is logged to two sinks:

1. **NDJSON file** on the host filesystem (one file per session, append-only). This is the primary audit trail and the format included in session exports.
2. **SQLite `action_log` table** (for in-app querying, e.g., investigation memory).

Each log entry follows a consistent schema:

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "timestamp": "ISO-8601",
  "action_type": "node_expand | copilot_query | filter_apply | finding_save | ...",
  "actor": "user | system",
  "payload": { },
  "result_summary": { },
  "guardrail_warnings": []
}
```

Writes to both sinks are async (fire-and-forget on a background task). A logging failure never blocks a user action.

* * *

## 4. Frontend Architecture

### 4.1 State Slices (Zustand)

```
┌──────────────────────────────────────────────────────┐
│                    Zustand Store                     │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ graphSlice │  │sessionSlice│  │  uiSlice      │  │
│  │            │  │            │  │               │  │
│  │ nodes[]    │  │ id         │  │ selectedIds[] │  │
│  │ edges[]    │  │ preset     │  │ panelStates   │  │
│  │ positions  │  │ findings[] │  │ banners[]     │  │
│  │ filters    │  │ actionLog[]│  │ inspectorTab  │  │
│  └────────────┘  └────────────┘  └───────────────┘  │
│                                                      │
│  ┌────────────────┐  ┌─────────────────────────┐     │
│  │ copilotSlice   │  │  configSlice            │     │
│  │  (Phase 2)     │  │                         │     │
│  │ messages[]     │  │  activePreset           │     │
│  │ isStreaming     │  │  advancedMode: boolean  │     │
│  │ pendingDelta   │  │  modelAssignments       │     │
│  └────────────────┘  └─────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

**Cross-slice rule:** Slices may _read_ each other (e.g., `copilotSlice` reads `graphSlice.nodes` to build context), but writes target a single slice. The one exception is "accept graph delta" — the copilot slice clears `pendingDelta` and the graph slice applies the delta in a single dispatched action.

### 4.2 Canvas ↔ State Synchronisation

Cytoscape.js maintains its own internal state (positions, styles). The Zustand `graphSlice` is the source of truth for _what_ is on the canvas (node/edge identity and properties). Cytoscape is the source of truth for _where_ things are (positions, viewport).

Sync protocol:

1. **Inbound (store → Cytoscape):** When `graphSlice.nodes` or `graphSlice.edges` change, a React effect diffs the current Cytoscape elements against the store and applies `cy.add()` / `cy.remove()` for the delta. Batch operations use `cy.startBatch()` / `cy.endBatch()` to suppress intermediate layout recalculations.
2. **Outbound (Cytoscape → store):** Position changes (from layout completion or user drag) are debounced (200ms) and written back to `graphSlice.positions`. This map is what gets serialised into session exports.
3. **Selection:** Cytoscape's `tap` event updates `uiSlice.selectedIds`. The Inspector subscribes to this slice.

### 4.3 Component Tree (simplified)

```
<App>
  <Toolbar />
  <MainLayout>
    <Navigator>
      <SearchPanel />
      <FilterPanel />
      <FindingsPanel />
    </Navigator>
    <CanvasContainer>
      <CytoscapeCanvas />         ← Cytoscape mount point
      <CanvasBanners />           ← Guardrail warnings overlay
      <DeltaPreview />            ← Phase 2: ghost nodes/edges pending commit
    </CanvasContainer>
    <Inspector>
      <NodeDetail />
      <EdgeDetail />
      <EvidencePanel />           ← Phase 2
    </Inspector>
  </MainLayout>
  <CopilotPanel />                ← Phase 2
</App>
```

### 4.4 Graph Delta Preview (Phase 2)

When the Copilot proposes new nodes/edges, they are rendered on the canvas as **ghost elements** — visually distinct (dashed borders, reduced opacity) and non-interactive until committed. This uses Cytoscape's class system:

```
cy.add(deltaElements).addClass('ghost');
```

On user accept: remove the `ghost` class and merge into `graphSlice`. On discard: `cy.remove('.ghost')` and clear `copilotSlice.pendingDelta`.

* * *

## 5. API Surface

All endpoints are prefixed with `/api/v1`. Versioning is path-based and incremented only on breaking changes.

### 5.1 Phase 1 Endpoints

**Graph**

| Method | Path                               | Purpose                                     |
| ------ | ---------------------------------- | ------------------------------------------- |
| GET    | `/graph/schema`                    | Database Overview: labels, types, counts    |
| GET    | `/graph/schema/samples/{label}`    | Sample nodes for a label                    |
| GET    | `/graph/schema/samples/rel/{type}` | Sample relationships for a type             |
| POST   | `/graph/search`                    | Full-text search for seed nodes             |
| POST   | `/graph/expand`                    | Expand from node(s) by type and hop count   |
| POST   | `/graph/paths`                     | Shortest / all-shortest paths between nodes |
| POST   | `/graph/query`                     | (Advanced Mode) Raw read-only Cypher        |

**Sessions**

| Method | Path                    | Purpose                                       |
| ------ | ----------------------- | --------------------------------------------- |
| POST   | `/sessions`             | Create new session                            |
| GET    | `/sessions/{id}`        | Load session state                            |
| PUT    | `/sessions/{id}`        | Update session (canvas state, config)         |
| DELETE | `/sessions/{id}`        | Delete session                                |
| POST   | `/sessions/{id}/export` | Export to `.g-lab-session` archive            |
| POST   | `/sessions/import`      | Import from archive                           |
| POST   | `/sessions/{id}/reset`  | Reset (clear canvas + history, keep findings) |

**Findings**

| Method | Path                            | Purpose                                 |
| ------ | ------------------------------- | --------------------------------------- |
| GET    | `/sessions/{id}/findings`       | List durable findings                   |
| POST   | `/sessions/{id}/findings`       | Create finding (with optional snapshot) |
| PUT    | `/sessions/{id}/findings/{fid}` | Update finding                          |
| DELETE | `/sessions/{id}/findings/{fid}` | Delete finding                          |

### 5.2 Phase 2 Endpoints

| Method | Path                            | Purpose                                  |
| ------ | ------------------------------- | ---------------------------------------- |
| POST   | `/copilot/query`                | Submit query; returns SSE stream         |
| GET    | `/copilot/history/{session_id}` | Retrieve conversation history            |
| GET    | `/config/presets`               | List presets (system + user)             |
| POST   | `/config/presets`               | Create user preset                       |
| PUT    | `/config/presets/{id}`          | Update user preset                       |
| DELETE | `/config/presets/{id}`          | Delete user preset (system presets: 403) |
| GET    | `/config/models`                | List available models via OpenRouter     |

### 5.3 Phase 3 Endpoints

| Method | Path                                   | Purpose                                 |
| ------ | -------------------------------------- | --------------------------------------- |
| GET    | `/documents/libraries`                 | List library entries                    |
| POST   | `/documents/libraries`                 | Create library entry                    |
| DELETE | `/documents/libraries/{id}`            | Delete library entry + vectors          |
| POST   | `/documents/libraries/{id}/upload`     | Upload document(s) to library entry     |
| DELETE | `/documents/libraries/{id}/docs/{did}` | Remove document from entry              |
| POST   | `/documents/libraries/{id}/attach`     | Attach library entry to current session |
| POST   | `/documents/libraries/detach`          | Detach current library entry            |

### 5.4 Response Conventions

All responses follow a consistent envelope:

```json
{
  "data": { },
  "warnings": [],
  "meta": {
    "request_id": "uuid",
    "duration_ms": 142
  }
}
```

Error responses:

```json
{
  "error": {
    "code": "GUARDRAIL_EXCEEDED",
    "message": "Expansion would add 45 nodes but only 12 slots remain.",
    "detail": {
      "requested": 45,
      "remaining": 12,
      "hard_limit": 500,
      "current": 488
    }
  },
  "meta": { "request_id": "uuid" }
}
```

HTTP status codes: `200` success, `201` created, `400` validation error, `409` guardrail conflict, `422` unprocessable entity, `504` timeout (Neo4j or LLM).

### 5.5 SSE Protocol (Phase 2)

The Copilot stream (`POST /copilot/query`) returns Server-Sent Events with typed messages:

| Event type    | Payload                                                |
| ------------- | ------------------------------------------------------ |
| `text_chunk`  | `{ "content": "..." }`                                 |
| `evidence`    | `{ "sources": [...] }` (graph paths or doc chunk refs) |
| `graph_delta` | `{ "add_nodes": [...], "add_edges": [...] }`           |
| `confidence`  | `{ "score": 0.72, "band": "high" }`                    |
| `status`      | `{ "stage": "routing"                                  |
| `done`        | `{}`                                                   |
| `error`       | `{ "code": "...", "message": "..." }`                  |

The frontend assembles these incrementally. `text_chunk` events are appended to the visible response as they arrive. `graph_delta` is held in `copilotSlice.pendingDelta` and rendered as ghost elements. `done` finalises the response.

* * *

## 6. Data Models

### 6.1 SQLite Schema

```sql
-- Sessions
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL,       -- ISO-8601
    updated_at      TEXT NOT NULL,
    preset_id       TEXT,
    canvas_state    TEXT NOT NULL,       -- JSON: nodes, edges, positions, viewport
    config          TEXT NOT NULL,       -- JSON: active guardrail overrides, model assignments
    status          TEXT NOT NULL DEFAULT 'active'  -- active | closed
);

-- Durable Findings
CREATE TABLE findings (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,                -- Markdown
    snapshot_png    BLOB,               -- Canvas snapshot (optional)
    canvas_context  TEXT                 -- JSON: node/edge IDs visible at save time
);

-- Action Log
CREATE TABLE action_log (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp       TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    actor           TEXT NOT NULL,       -- 'user' | 'system'
    payload         TEXT,               -- JSON
    result_summary  TEXT,               -- JSON
    guardrail_warnings TEXT             -- JSON array
);
CREATE INDEX idx_action_log_session ON action_log(session_id, timestamp);

-- Configuration Presets (Phase 2)
CREATE TABLE presets (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    is_system       INTEGER NOT NULL DEFAULT 0,
    config          TEXT NOT NULL        -- JSON: full preset definition
);

-- Document Libraries (Phase 3)
CREATE TABLE document_libraries (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    doc_count       INTEGER NOT NULL DEFAULT 0,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    parse_quality   TEXT,               -- 'high' | 'standard' | 'basic'
    indexed_at      TEXT
);

CREATE TABLE documents (
    id              TEXT PRIMARY KEY,
    library_id      TEXT NOT NULL REFERENCES document_libraries(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    file_hash       TEXT NOT NULL,       -- SHA-256, for dedup
    parse_tier      TEXT NOT NULL,       -- 'high' | 'standard' | 'basic'
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    uploaded_at     TEXT NOT NULL
);

-- Session ↔ Library attachment (Phase 3)
CREATE TABLE session_library_attachments (
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    library_id      TEXT NOT NULL REFERENCES document_libraries(id) ON DELETE CASCADE,
    attached_at     TEXT NOT NULL,
    PRIMARY KEY (session_id)            -- A session attaches to at most one library
);
```

### 6.2 Canvas State (JSON, stored in `sessions.canvas_state`)

```json
{
  "schema_version": 1,
  "nodes": [
    {
      "id": "neo4j-element-id",
      "labels": ["Person"],
      "properties": { "name": "Alice", "role": "Director" },
      "position": { "x": 120.5, "y": 340.2 }
    }
  ],
  "edges": [
    {
      "id": "neo4j-element-id",
      "type": "OWNS",
      "source": "node-id",
      "target": "node-id",
      "properties": { "since": 2019 }
    }
  ],
  "viewport": { "zoom": 1.2, "pan": { "x": -50, "y": 100 } },
  "filters": {
    "hidden_labels": ["Address"],
    "hidden_types": ["LOCATED_AT"]
  }
}
```

### 6.3 Session Export Archive (`.g-lab-session`)

A `.g-lab-session` file is a ZIP archive with a defined structure:

```
session-export/
├── manifest.json           # Schema version, export timestamp, G-Lab version
├── session.json            # Session metadata + config
├── canvas.json             # Full canvas state
├── action_log.ndjson       # Complete action log
├── findings/
│   ├── index.json          # Finding metadata array
│   └── snapshots/          # PNG files, named by finding ID
│       ├── f1.png
│       └── f2.png
└── vector_manifest.json    # (Phase 3) Library entry name, doc list — reference only
```

On import, the backend validates `manifest.json` against supported schema versions. Incompatible versions are rejected with a descriptive error. Forward-compatible minor versions (e.g., new optional fields) are accepted with a warning.

* * *

## 7. Copilot Pipeline (Phase 2)

### 7.1 Orchestration

The Copilot pipeline is orchestrated by the backend, not by chained LLM calls. Each step is a discrete service call with explicit inputs and outputs.

```
User query + graph context (visible nodes/edges summary)
  │
  ▼
┌──────────────────────────────────────────────┐
│  1. ROUTER                                    │
│  Input:  user query, graph context summary    │
│  Output: structured intent                    │
│          { needs_graph: bool,                 │
│            needs_docs: bool,                  │
│            cypher_hint: str | null,           │
│            doc_query: str | null }            │
│  Model:  lightweight (e.g., Haiku-class)      │
│  Format: JSON structured output               │
└──────────────┬───────────────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
┌─────────────┐ ┌──────────────┐
│ 2a. GRAPH   │ │ 2b. DOCUMENT │  ← Phase 3
│ RETRIEVAL   │ │ RETRIEVAL    │
│             │ │              │
│ Generate    │ │ Vector search│
│ Cypher from │ │ + rerank     │
│ intent +    │ │              │
│ schema      │ │ Input: query │
│             │ │ Output: top-k│
│ Execute     │ │ chunks w/    │
│ read-only   │ │ metadata     │
│             │ │              │
│ Model:      │ │ Model: embed │
│ balanced    │ │ + reranker   │
└──────┬──────┘ └──────┬───────┘
       │               │
       └───────┬───────┘
               ▼
┌──────────────────────────────────────────────┐
│  3. SYNTHESISER                               │
│  Input:  user query, graph results,           │
│          doc chunks (if any), graph context    │
│  Output: SSE stream of:                       │
│          - text answer                        │
│          - evidence map                       │
│          - graph delta (proposed new nodes)    │
│          - confidence score + band            │
│  Model:  strongest available                  │
└──────────────────────────────────────────────┘
```

### 7.2 Graph Retrieval — Cypher Generation

The Graph Retrieval role receives the router's intent and the database schema (labels, relationship types, property keys — cached from the Database Overview) and generates a read-only Cypher query.

**Safety layers:**

1. The LLM prompt includes explicit instructions to generate only `MATCH` / `RETURN` / `WHERE` / `WITH` / `ORDER BY` / `LIMIT` clauses.
2. The generated Cypher is passed through the same static sanitiser used for user-submitted raw queries (Section 3.3).
3. Execution uses a read transaction with the configured timeout.

If the sanitiser rejects the generated query, the system retries once with an amended prompt. A second rejection returns an error to the Synthesiser, which informs the user.

### 7.3 Confidence Scoring

Confidence is computed by the Synthesiser as a structured output field. The prompt instructs the model to assess:

- How many claims in its answer are directly supported by retrieved evidence?
- Are there claims that required inference beyond the evidence?
- Were any retrieved results contradictory?

The score (0.0–1.0) is bucketed into bands: High (>0.70), Medium (0.40–0.70), Low (<0.40).

**Re-retrieval:** If the initial confidence is Low, the backend automatically triggers one re-retrieval cycle. It amends the retrieval query (expanding hop count by 1 or increasing document top-k by 5) and re-runs steps 2–3. The SSE stream emits a `status: re-retrieving` event so the frontend can show an inline indicator. If re-retrieval still yields Low confidence, the best answer is returned with an explicit low-confidence flag.

### 7.4 Model Assignment

Each pipeline role has a model slot:

| Role            | Default (Standard) | Configurable in Advanced |
| --------------- | ------------------ | ------------------------ |
| Router          | Fast/cheap model   | Yes                      |
| Graph Retrieval | Balanced model     | Yes                      |
| Synthesiser     | Strongest model    | Yes                      |

Defaults are resolved at startup from a hardcoded fallback table. The model registry fetches available models from OpenRouter's `/models` endpoint and caches the result for 1 hour. Users select from this list in Advanced Mode.

**Token budgets:** Each role has a max output token limit configured per preset (e.g., Router: 256 tokens, Graph Retrieval: 512, Synthesiser: 4096). These are soft limits adjustable in Advanced Mode.

* * *

## 8. Document Ingestion Pipeline (Phase 3)

### 8.1 Three-Tier Parse Strategy

Documents are processed through a tiered pipeline. Each tier is attempted in order; the first successful parse wins.

```
Upload (any supported format)
  │
  ▼
┌─────────────────────────────┐
│ Tier 1: Docling             │
│ (structural extraction)     │──── success → High quality
│                             │
│ Auto-detects format.        │
│ Extracts: headings, tables, │
│ lists, reading order        │
└──────────┬──────────────────┘
           │ failure
           ▼
┌─────────────────────────────┐
│ Tier 2: Unstructured        │
│ (partition + categorize)    │──── success → Standard quality
│                             │
│ Auto-detects format.        │
│ Extracts: text blocks with  │
│ basic element types         │
└──────────┬──────────────────┘
           │ failure
           ▼
┌─────────────────────────────┐
│ Tier 3: Raw fallback        │
│ (plain text extraction)     │──── success → Basic quality
│                             │
│ PyPDF2 (PDF), python-docx   │
│ (DOCX), UTF-8 read (other) │
└─────────────────────────────┘

Supported file types: PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, ODT, ODP, ODS,
RTF, EPUB, TXT, Markdown, RST, Org, AsciiDoc, HTML, XML, JSON, CSV, TSV,
EML, MSG. The tiered parsers auto-detect format from file content and
extension — not all tiers support every format, but the cascade ensures
best-effort extraction for any supported type.
```

### 8.2 Chunking

After parsing, the extracted text is split into chunks using recursive character splitting:

- **Chunk size:** 512 tokens (measured by the embedding model's tokeniser).
- **Overlap:** 64 tokens.
- **Split hierarchy:** Paragraph boundary → sentence boundary → word boundary.

Each chunk retains metadata: `document_id`, `library_id`, `page_number` (if available), `section_heading` (if Tier 1), `chunk_index`, `parse_tier`.

### 8.3 Embedding + Storage

Chunks are embedded using the configured model (`all-MiniLM-L6-v2` default) and stored in ChromaDB. The ChromaDB collection ID corresponds to the library entry ID.

**Deduplication:** On re-upload, the document's SHA-256 hash is compared. If it matches an existing document in the same library entry, all existing chunks for that document are deleted before re-indexing.

### 8.4 Retrieval at Query Time

When the Router indicates `needs_docs: true`:

1. The doc query (from the Router) is embedded using the same model.
2. ChromaDB returns the top-k nearest chunks (k from active preset, default 5).
3. A cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) re-scores and selects the top reranker-k chunks (default 3).
4. Selected chunks, with metadata, are passed to the Synthesiser as document context.

* * *

## 9. Guardrail Enforcement

Guardrails are enforced in the backend at the service layer, never in the frontend alone. The frontend mirrors guardrail state for UX purposes (warnings, disabled buttons) but the backend is the authority.

### 9.1 Enforcement Points

| Guardrail                     | Enforcement point         | Mechanism                                    |
| ----------------------------- | ------------------------- | -------------------------------------------- |
| Max canvas nodes (500)        | `guardrails.py` pre-check | Count current + requested vs. limit          |
| Max hops (5)                  | `guardrails.py` pre-check | Validate hop param before query construction |
| Max nodes per expansion (100) | `guardrails.py` pre-check | `LIMIT` clause injected into Cypher          |
| Cypher timeout (30s)          | Neo4j driver config       | `timeout` parameter on transaction           |
| Copilot timeout (120s)        | `asyncio.wait_for()`      | Wraps entire pipeline execution              |
| Concurrent Copilot requests   | Asyncio semaphore (1)     | Serialises pipeline entry                    |
| Doc upload size (50 MB)       | FastAPI middleware        | `Request.content_length` check               |
| Docs per library (100)        | `guardrails.py` pre-check | Count before accepting upload                |

### 9.2 Soft Limit Resolution

For requests that specify parameters within the overridable range, the backend resolves the effective limit by:

1. Reading the active session's preset.
2. Checking for per-session overrides (Advanced Mode).
3. Clamping to the hard limit.

```python
effective = min(
    request.hop_count or preset.default_hops,
    hard_limits.MAX_HOPS
)
```

* * *

## 10. Security

### 10.1 Threat Model

G-Lab runs locally. The primary threats are:

1. **Credential leakage** — Neo4j and OpenRouter credentials stored on disk.
2. **Cypher injection** — Malicious input producing write queries.
3. **LLM prompt injection** — User-uploaded documents or graph data containing adversarial text that manipulates the Copilot.

### 10.2 Mitigations

**Credentials:** Neo4j credentials and the OpenRouter API key are stored in a `.env` file. The API key is encrypted at rest using Fernet (symmetric encryption) with a key derived from a machine-specific seed. This is not high-security HSM-level protection — it prevents casual exposure in file browsers and accidental commits.

**Cypher injection:** Defence-in-depth via three layers (Section 3.3): read-only driver mode, static query sanitisation, read transaction enforcement. The sanitiser uses an allowlist approach — only permitted clauses pass through.

**Prompt injection:** The Copilot pipeline uses clearly delineated system/user message boundaries. Retrieved evidence (graph data, document chunks) is injected into a designated context section of the prompt, never into the system message. This doesn't eliminate prompt injection risk but limits the blast radius. Document content is treated as untrusted data in all prompt templates.

### 10.3 Network Exposure

The Docker Compose configuration binds only to `127.0.0.1`. No port is exposed to the network by default. Users who need remote access (e.g., accessing G-Lab from another machine on the same network) must explicitly override the bind address.

* * *

## 11. Deployment

### 11.1 Docker Compose Topology

```yaml
services:
  frontend:
    build: ./frontend
    ports:
      - "127.0.0.1:5173:5173"
    depends_on:
      - backend

  backend:
    build: ./backend
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - glab-data:/data               # SQLite DB + NDJSON logs + exports
    environment:
      - NEO4J_URI=${NEO4J_URI}
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}    # Phase 2
    depends_on:
      - chromadb                        # Phase 3

  chromadb:                             # Phase 3
    image: chromadb/chroma:latest
    ports:
      - "127.0.0.1:8100:8000"
    volumes:
      - chroma-data:/chroma/chroma

volumes:
  glab-data:
  chroma-data:
```

**Neo4j is not in this Compose file.** The user manages their own Neo4j instance. G-Lab connects to it via the URI in the environment variable.

### 11.2 Startup Sequence

1. Backend starts, connects to Neo4j (retries with exponential backoff, 5 attempts, max 30s total).
2. If Neo4j is unreachable after retries: backend starts in degraded mode (session restore works in read-only review mode; graph endpoints return `503`).
3. Backend runs SQLite migrations (Alembic, auto-apply on startup).
4. Frontend serves the SPA. On load, it fetches `/api/v1/sessions/last-active` to restore the previous session.
5. If session restore fails (corrupt state), the frontend shows an error and offers to start fresh (per PRODUCT.md Section 8).

### 11.3 Configuration

All configuration is via environment variables, with sensible defaults. No config file is required for Phase 1.

| Variable              | Required | Default                        | Phase |
| --------------------- | -------- | ------------------------------ | ----- |
| `NEO4J_URI`           | Yes      | —                              | 1     |
| `NEO4J_USER`          | Yes      | —                              | 1     |
| `NEO4J_PASSWORD`      | Yes      | —                              | 1     |
| `GLAB_DATA_DIR`       | No       | `/data`                        | 1     |
| `GLAB_LOG_LEVEL`      | No       | `INFO`                         | 1     |
| `OPENROUTER_API_KEY`  | Phase 2  | —                              | 2     |
| `OPENROUTER_BASE_URL` | No       | `https://openrouter.ai/api/v1` | 2     |
| `CHROMA_HOST`         | No       | `chromadb`                     | 3     |
| `CHROMA_PORT`         | No       | `8000`                         | 3     |
| `EMBEDDING_MODEL`     | No       | `all-MiniLM-L6-v2`             | 3     |

* * *

## 12. Testing Strategy

### 12.1 Test Layers

| Layer         | Tool                    | Scope                                                     |
| ------------- | ----------------------- | --------------------------------------------------------- |
| Unit          | pytest                  | Service logic, guardrail enforcement, Cypher sanitisation |
| Integration   | pytest + testcontainers | Neo4j queries against a real instance, SQLite persistence |
| API           | pytest + httpx          | Endpoint contracts, error responses, SSE streaming        |
| Frontend unit | Vitest                  | Zustand store logic, utility functions                    |
| Component     | Testing Library         | Panel rendering, user interactions                        |
| E2E           | Playwright              | Full investigation flow: seed → expand → export           |

### 12.2 Test Data

Integration tests use a small, deterministic Neo4j fixture (loaded via Cypher scripts in `tests/fixtures/`). The fixture contains ~50 nodes and ~80 relationships across 3–4 labels, enough to exercise expansion, filtering, path discovery, and guardrail limits.

E2E tests run against the full Docker Compose stack with this fixture pre-loaded.

### 12.3 CI Pipeline

```
lint (ruff + eslint) → type-check (mypy + tsc) → unit → integration → e2e
```

Integration and E2E stages use Docker Compose with test-specific overrides. The pipeline runs on every push. E2E is gated to `main` branch and release tags to keep cycle time reasonable on feature branches.

* * *

## 13. Phase Boundaries

Each phase has a clear architectural boundary. Later phases add containers and modules but do not restructure earlier ones.

**Phase 1 ships:**

- `frontend/`, `backend/` (routers: graph, sessions, findings)
- `services/`: neo4j_service, session_service, guardrails, action_log
- SQLite schema (sessions, findings, action_log tables)
- Docker Compose: frontend + backend (2 containers)
- Test suite: unit + integration + E2E for graph workbench

**Phase 2 adds:**

- `routers/copilot.py`, `routers/config_presets.py`
- `services/copilot/` (router, graph_retrieval, synthesiser, openrouter)
- SQLite migration: add `presets` table
- OpenRouter dependency (env var)
- SSE streaming infrastructure
- Test suite additions: copilot pipeline unit tests, SSE integration tests

**Phase 3 adds:**

- `routers/documents.py`
- `services/documents/` (ingestion, chunking, retrieval)
- SQLite migration: add `document_libraries`, `documents`, `session_library_attachments` tables
- ChromaDB container in Docker Compose
- Document ingestion dependencies (Docling, Unstructured, PyPDF2)
- Test suite additions: ingestion pipeline tests, retrieval integration tests

No phase requires restructuring code from a prior phase. The backend's modular router/service architecture ensures that new capabilities are additive.

* * *

## 14. Canonical Type Contracts

This section is the **single source of truth** for the data types shared between backend and frontend. When implementing schemas in `backend/app/models/schemas.py` or `frontend/src/lib/types.ts`, follow these definitions exactly. `STRUCTURE_PH1.md` references this section rather than repeating schemas.

### 14.1 API Response Envelope

Every endpoint returns this shape. The frontend `client.ts` unwraps it.

```typescript
// Frontend: src/lib/types.ts
interface ApiResponse<T> {
  data: T;
  warnings: string[];
  meta: {
    request_id: string;
    duration_ms: number;
  };
}

interface ApiError {
  error: {
    code: string;       // e.g. "GUARDRAIL_EXCEEDED", "NEO4J_TIMEOUT"
    message: string;
    detail?: Record<string, unknown>;
  };
  meta: { request_id: string };
}
```

```python
# Backend: app/utils/response.py
def envelope(data: Any, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "warnings": warnings or [],
        "meta": {
            "request_id": str(uuid4()),
            "duration_ms": 0,  # filled by middleware
        },
    }
```

### 14.2 Graph Data Types

Shared across API, store, and Cytoscape sync layer.

```typescript
// Frontend: src/lib/types.ts
interface GraphNode {
  id: string;                       // Neo4j element ID
  labels: string[];
  properties: Record<string, unknown>;
  position?: { x: number; y: number };
}

interface GraphEdge {
  id: string;
  type: string;
  source: string;                   // node ID
  target: string;                   // node ID
  properties: Record<string, unknown>;
}

interface CanvasState {
  schema_version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  viewport: { zoom: number; pan: { x: number; y: number } };
  filters: {
    hidden_labels: string[];
    hidden_types: string[];
  };
}
```

```python
# Backend: app/models/schemas.py
class GraphNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]

class GraphEdge(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any]
```

### 14.3 Request/Response Schemas

```python
# Backend: app/models/schemas.py

class SearchRequest(BaseModel):
    query: str
    labels: list[str] | None = None   # filter to specific labels
    limit: int = Field(default=20, le=100)

class SearchResponse(BaseModel):
    nodes: list[GraphNode]

class ExpandRequest(BaseModel):
    node_ids: list[str]
    relationship_types: list[str] | None = None   # None = all types
    hops: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=25, ge=1, le=100)
    current_canvas_count: int                      # for guardrail pre-check

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
    paths: list[list[GraphNode | GraphEdge]]       # alternating node-edge-node sequences
    nodes: list[GraphNode]                          # deduplicated nodes across all paths
    edges: list[GraphEdge]                          # deduplicated edges across all paths

class SchemaResponse(BaseModel):
    labels: list[LabelInfo]
    relationship_types: list[RelTypeInfo]

class LabelInfo(BaseModel):
    name: str
    count: int | None                              # None if count query timed out
    property_keys: list[str]

class RelTypeInfo(BaseModel):
    name: str
    count: int | None
    property_keys: list[str]

class SessionCreate(BaseModel):
    name: str

class SessionResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    status: str
    canvas_state: CanvasState
    config: dict[str, Any]

class FindingCreate(BaseModel):
    title: str
    body: str | None = None
    snapshot_png: str | None = None                # base64-encoded
    canvas_context: list[str] | None = None        # node/edge IDs visible at save time

class FindingResponse(BaseModel):
    id: str
    session_id: str
    created_at: str
    updated_at: str
    title: str
    body: str | None
    has_snapshot: bool
    canvas_context: list[str] | None
```

### 14.4 Guardrail Service Interface

```python
# Backend: app/services/guardrails.py

@dataclass
class GuardrailResult:
    allowed: bool
    warnings: list[str]
    detail: dict[str, Any] | None = None  # populated on rejection

class GuardrailService:
    HARD_LIMITS = {
        "max_canvas_nodes": 500,
        "max_hops": 5,
        "max_nodes_per_expansion": 100,
        "cypher_timeout_ms": 30_000,
    }

    def check_expansion(
        self, current_count: int, requested_limit: int, preset_limit: int
    ) -> GuardrailResult: ...

    def check_hops(self, requested: int, preset_default: int) -> GuardrailResult: ...

    def resolve_effective_limit(
        self, requested: int | None, preset_default: int, hard_max: int
    ) -> int: ...
```

### 14.5 Neo4j Service Interface

```python
# Backend: app/services/neo4j_service.py

class Neo4jService:
    async def connect(self, uri: str, user: str, password: str) -> None: ...
    async def close(self) -> None: ...
    def is_connected(self) -> bool: ...

    async def get_schema(self) -> SchemaResponse: ...
    async def get_samples(self, label: str, limit: int = 5) -> list[GraphNode]: ...
    async def get_relationship_samples(
        self, rel_type: str, limit: int = 5
    ) -> list[dict]: ...

    async def search(
        self, query: str, labels: list[str] | None, limit: int
    ) -> list[GraphNode]: ...

    async def expand(
        self, node_ids: list[str], rel_types: list[str] | None,
        hops: int, limit: int, timeout_ms: int
    ) -> tuple[list[GraphNode], list[GraphEdge]]: ...

    async def find_paths(
        self, source_id: str, target_id: str, max_hops: int,
        mode: str, timeout_ms: int
    ) -> tuple[list[list], list[GraphNode], list[GraphEdge]]: ...

    async def execute_raw(self, cypher: str, timeout_ms: int) -> list[dict]: ...
```

* * *

## Appendix A: Key Trade-offs & Decisions

| Decision         | Chosen            | Alternative considered          | Rationale                                                                                          |
| ---------------- | ----------------- | ------------------------------- | -------------------------------------------------------------------------------------------------- |
| Canvas renderer  | Cytoscape.js      | D3, Sigma.js, react-force-graph | Best balance of layout algorithms, interaction model, and extension ecosystem for investigation UX |
| State management | Zustand           | Redux, Jotai, MobX              | Lightweight, minimal boilerplate, selector-based subscriptions fit canvas update patterns          |
| Backend language | Python (FastAPI)  | Node.js, Go                     | First-class Neo4j driver, LLM SDK ecosystem, document processing libraries                         |
| Session storage  | SQLite            | PostgreSQL, file-based JSON     | Zero-ops, embedded, WAL mode for async reads, portable for exports                                 |
| Vector store     | ChromaDB          | Qdrant, Weaviate, pgvector      | Embedded model support, simple Python client, minimal operational overhead                         |
| LLM gateway      | OpenRouter        | Direct provider APIs, LiteLLM   | Single API surface, user model choice, no per-provider integration burden                          |
| Deployment       | Docker Compose    | Kubernetes, bare metal          | Right-sized for single-user self-hosted. K8s is overkill; bare metal is too fragile                |
| Auth             | None (local-only) | Basic auth, OAuth               | Single-user, localhost-bound. Auth adds complexity without matching the threat model               |
