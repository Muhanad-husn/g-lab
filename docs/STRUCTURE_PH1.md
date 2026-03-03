G-Lab — STRUCTURE_PH1.md
=========================

> **Status:** v2.0 — March 2026
> **Ownership:** This document defines _where_ to start and _in what order_ to build Phase 1. `PRODUCT.md` defines what and why. `ARCHITECTURE.md` defines how and holds all canonical schemas (§14). `backend/CLAUDE.md` and `frontend/CLAUDE.md` hold coding conventions.
> **Scope:** Phase 1 only.

* * *

## 1. Build Order

Build proceeds in **7 stages**. Each stage produces a runnable or testable increment. Dependencies flow downward — never start a stage until its prerequisites are done.

```
Stage 1: Foundation (backend skeleton + DB)
    │
    ▼
Stage 2: Neo4j Integration
    │
    ▼
Stage 3: Session Lifecycle ──────────────┐
    │                                    │
    ▼                                    ▼
Stage 4: Graph Operations          Stage 5: Frontend Shell
    │                                    │
    └──────────┬─────────────────────────┘
               ▼
         Stage 6: Canvas Integration
               │
               ▼
         Stage 7: Polish & Export
```

**Parallel work streams:**

- **Stream A (backend):** Stages 1–4. Full backend without touching React.
- **Stream B (frontend):** Stage 5 starts when Stage 3 is done (needs session API). Mock graph data.
- **Stream C (infra):** Dockerfiles, Compose, CI — parallel with Stage 1.

* * *

### Stage 1 — Foundation

**Goal:** Backend boots, connects to nothing, serves health check. SQLite ready.

**Depends on:** Nothing.

**Files:**

1. `backend/app/config.py` — Pydantic `Settings` class reading env vars with defaults
2. `backend/app/models/enums.py` — `ActionType`, `SessionStatus` enums
3. `backend/app/models/db.py` — SQLAlchemy models for `sessions`, `findings`, `action_log`; engine factory with WAL mode. Schema: ARCHITECTURE.md §6.1
4. `alembic/versions/001_initial_schema.py` — Initial migration
5. `backend/app/utils/response.py` — Envelope helper. Contract: ARCHITECTURE.md §14.1
6. `backend/app/main.py` — FastAPI app with lifespan (init DB on startup), CORS middleware, health endpoint
7. `backend/app/dependencies.py` — `get_db` dependency (SQLAlchemy async session)
8. `backend/Dockerfile` — Python 3.12 slim, install deps, run uvicorn
9. `docker-compose.yml` — Backend service only

**Test:** `pytest tests/unit/` — DB models create tables, envelope helper formats correctly.

**Acceptance:** `docker compose up` → backend starts → `GET /health` returns `200`.

* * *

### Stage 2 — Neo4j Integration

**Goal:** Backend can connect to Neo4j, run schema introspection, and execute read-only queries.

**Depends on:** Stage 1.

**Files:**

1. `backend/app/utils/cypher.py` — Cypher sanitiser (allowlist approach). See `backend/CLAUDE.md` for the allowlist.
2. `backend/app/services/neo4j_service.py` — Driver lifecycle, schema introspection, search, expand, paths, raw query. Interface: ARCHITECTURE.md §14.5
3. `backend/app/dependencies.py` — Add `get_neo4j` dependency
4. Update `main.py` lifespan — Connect to Neo4j on startup (degraded mode on failure)
5. `backend/app/services/guardrails.py` — Hard/soft limit checks. Interface: ARCHITECTURE.md §14.4

**Test:** `pytest tests/unit/test_cypher_sanitiser.py` (pure logic), `pytest tests/integration/test_neo4j_service.py` (testcontainers with seed fixture).

**Acceptance:** Backend connects to a local Neo4j, `neo4j_service.get_schema()` returns real data.

* * *

### Stage 3 — Session Lifecycle

**Goal:** Sessions can be created, loaded, updated, reset, and deleted via API.

**Depends on:** Stage 1.

**Files:**

1. `backend/app/services/session_service.py` — `create()`, `get()`, `update()`, `delete()`, `reset()`, `get_last_active()`
2. `backend/app/services/finding_service.py` — CRUD operations, snapshot storage as BLOB
3. `backend/app/services/action_log.py` — Dual-sink logging (NDJSON + SQLite). See `backend/CLAUDE.md` for logging rules.
4. `backend/app/models/schemas.py` — Session and finding schemas. Contract: ARCHITECTURE.md §14.3
5. `backend/app/routers/sessions.py` — All session endpoints per ARCHITECTURE.md §5.1
6. `backend/app/routers/findings.py` — All findings endpoints per ARCHITECTURE.md §5.1
7. Add routers to `main.py`

**Test:** `pytest tests/integration/test_session_service.py`, `pytest tests/api/test_session_endpoints.py`.

**Acceptance:** `POST /api/v1/sessions` creates a session, `GET` returns it, `POST .../reset` clears canvas but keeps findings.

* * *

### Stage 4 — Graph Operations

**Goal:** All graph query endpoints work with guardrail enforcement.

**Depends on:** Stage 2, Stage 3 (needs session context for guardrail state).

**Files:**

1. `backend/app/models/schemas.py` — Add graph schemas. Contract: ARCHITECTURE.md §14.3
2. `backend/app/routers/graph.py` — All graph endpoints per ARCHITECTURE.md §5.1. Pattern: validate → guardrail check → service call → envelope response.
3. Update `guardrails.py` — Wire soft limit resolution (read preset from session config, clamp to hard limits)

**Test:** `pytest tests/unit/test_guardrails.py`, `pytest tests/api/test_graph_endpoints.py`.

**Acceptance:** `POST /api/v1/graph/expand` with `current_canvas_count: 490` and expansion returning 20 nodes → `409` with detail. Same request with count `480` → `200` with 20 nodes.

* * *

### Stage 5 — Frontend Shell

**Goal:** SPA renders the four-zone layout. No canvas yet — just panels, navigation, and API wiring.

**Depends on:** Stage 3 (needs session API to restore on load).

**Files:**

1. Scaffold: `npm create vite@latest`, install dependencies
2. `src/lib/types.ts` — Types per ARCHITECTURE.md §14.2
3. `src/lib/constants.ts` — Hard limits, default preset values
4. `src/api/client.ts` — Fetch wrapper: base URL, envelope unwrap, typed errors
5. `src/api/sessions.ts`, `src/api/graph.ts`, `src/api/findings.ts` — Typed API callers
6. `src/store/graphSlice.ts` — nodes, edges, positions, filters + actions
7. `src/store/sessionSlice.ts` — session, findings + actions
8. `src/store/uiSlice.ts` — selectedIds, panelStates, banners + actions
9. `src/store/configSlice.ts` — activePreset (hardcoded Standard Investigation for Phase 1)
10. `src/store/index.ts` — Combine slices
11. Layout: `Toolbar.tsx`, `MainLayout.tsx` (three-column with `react-resizable-panels`)
12. Navigator: `Navigator.tsx`, `SearchPanel.tsx`, `FilterPanel.tsx`, `FindingsPanel.tsx`, `DatabaseOverview.tsx`
13. Inspector: `Inspector.tsx`, `NodeDetail.tsx`, `EdgeDetail.tsx`
14. `src/hooks/useSessionRestore.ts` — Fetch last-active session on mount
15. `frontend/Dockerfile` — Node 20, Vite build, nginx serve
16. Update `docker-compose.yml` — Add frontend service

**Test:** `vitest` — store slice tests (add nodes, toggle filters, push banners).

**Acceptance:** `docker compose up` → browser shows four-zone layout, session restores from API, search panel sends requests.

* * *

### Stage 6 — Canvas Integration

**Goal:** Cytoscape renders the graph. Full investigation flow works: seed → expand → filter → inspect.

**Depends on:** Stage 4, Stage 5.

**Files:**

1. `src/lib/cytoscape.ts` — Instance factory, layout configs (CoSE-Bilkent default, concentric, breadthfirst)
2. `src/components/canvas/cytoscapeStyles.ts` — Node/edge visual styles, label rendering, selection highlight
3. `src/components/canvas/useCanvasSync.ts` — Inbound/outbound sync hook. See `frontend/CLAUDE.md` for Cytoscape rules.
4. `src/components/canvas/CytoscapeCanvas.tsx` — Mount Cytoscape, attach sync hook, layout on node changes
5. `src/components/canvas/CanvasBanners.tsx` — Guardrail warnings at 400/500 nodes
6. `src/hooks/useGraphActions.ts` — `expandNode()`, `searchAndSeed()`, `findPaths()` — API → store → layout
7. Wire SearchPanel → useGraphActions → canvas
8. Wire FilterPanel → graphSlice.setFilters → Cytoscape hides/shows
9. Wire Inspector → uiSlice.selectedIds → property display
10. Wire DatabaseOverview → `GET /graph/schema` → schema, metrics, sample tables

**Test:** Component tests for Inspector. E2E (Playwright): seed → expand → filter → inspect flow.

**Acceptance:** User searches a node name, drops it on canvas, expands 2 hops, filters by label, clicks a node, sees properties in Inspector.

* * *

### Stage 7 — Polish & Export

**Goal:** Session export/import, findings with snapshots, action logging, Docker Compose ready for distribution.

**Depends on:** Stage 6.

**Files:**

1. `backend/app/utils/export.py` — ZIP archive pack/unpack. Format: ARCHITECTURE.md §6.3
2. Wire export/import endpoints in `routers/sessions.py`
3. Canvas snapshot via `cy.png()` — send as base64 with finding creation
4. `FindingsPanel` — Create finding dialog (title, body, optional snapshot), list with thumbnails
5. `DatabaseOverview` — Pagination for sample data tables
6. Ensure all user actions call `action_log.log()` via background task
7. Session import validation: check `manifest.json` schema version, reject incompatible
8. Read-only review mode: frontend checks Neo4j status from backend health, disables actions when degraded
9. `.env.example`, `README.md` with quickstart instructions
10. `docker-compose.yml` final: both services, volumes, env var passthrough

**Test:** Full E2E: create session → investigate → save finding → export → delete → import → verify findings preserved.

**Acceptance:** Phase 1 validation criteria met — user connects to their Neo4j, explores with Database Overview, investigates, exports.