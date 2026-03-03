# G-Lab Phase 1 — Implementation Plan

## Context

G-Lab is a graph investigation workbench for data journalists and OSINT investigators. The project is fully scaffolded (all source files empty) with comprehensive documentation. This plan implements all 7 stages of Phase 1, broken into 23 runs of 3–6 files each.

**Key references:** `docs/ARCHITECTURE.md` §14 (type contracts), `backend/CLAUDE.md` (Neo4j/SQLite rules), `frontend/CLAUDE.md` (Cytoscape/store rules).

---

## Stage 1 — Foundation (3 runs)

### Run 1.1: Config, Enums, DB Models
- `backend/pyproject.toml` — deps: FastAPI, uvicorn, SQLAlchemy[asyncio], aiosqlite, neo4j, pydantic-settings, alembic, ruff, mypy, pytest, httpx
- `backend/app/__init__.py`, `backend/app/models/__init__.py` — package inits
- `backend/app/config.py` — Pydantic `Settings` (NEO4J_URI/USER/PASSWORD, GLAB_DATA_DIR=/data, GLAB_LOG_LEVEL=INFO)
- `backend/app/models/enums.py` — `ActionType` (node_expand, node_search, path_discovery, filter_apply, finding_save, session_create, session_reset, session_export, session_import, raw_query), `SessionStatus` (active, closed)
- `backend/app/models/db.py` — SQLAlchemy async models for `sessions`, `findings`, `action_log` per §6.1. Engine factory with WAL mode via event listener. All IDs as Text, datetimes as ISO-8601 Text, canvas_state/config as Text (JSON).

**Verify:** `pip install -e ".[dev]"` + import check

### Run 1.2: Alembic, Response Envelope, Dependencies
- `backend/alembic.ini` + `backend/alembic/env.py` — async Alembic setup
- `backend/alembic/versions/001_initial_schema.py` — creates sessions, findings, action_log tables + index
- `backend/app/utils/__init__.py`, `backend/app/utils/response.py` — `envelope(data, warnings)` and `error_response(code, message, detail)` per §14.1
- `backend/app/dependencies.py` — `get_db()` async generator, `get_settings()` cached

**Verify:** import check + envelope output test

### Run 1.3: FastAPI App, Docker, Tests
- `backend/app/main.py` — FastAPI with async lifespan (runs Alembic upgrade), CORS middleware, timing middleware (fills `duration_ms`), `/health` endpoint
- `backend/Dockerfile` — Python 3.12-slim, uvicorn
- `docker-compose.yml` — backend service, 127.0.0.1:8000, volume glab-data, env passthrough
- `.gitignore` — Python, Node, IDE, OS patterns
- `backend/tests/unit/test_response.py` — envelope shape, error shape, request_id is UUID

**Verify:** `pytest tests/unit/ -x -v`, `GET /health` returns 200

---

## Stage 2 — Neo4j Integration (3 runs)

### Run 2.1: Cypher Sanitiser
- `backend/app/utils/cypher.py` — `CypherSanitiser.sanitise()` with allowlist (MATCH, RETURN, WHERE, WITH, ORDER BY, LIMIT, OPTIONAL MATCH, UNWIND, CALL db.*, shortestPath, allShortestPaths). Rejects CREATE/MERGE/SET/DELETE/REMOVE/DROP/CALL{}/DETACH. Strips comments, rejects semicolons.
- `backend/app/utils/exceptions.py` — `CypherValidationError`, `GuardrailExceededError`, `Neo4jConnectionError`
- `backend/tests/unit/test_cypher_sanitiser.py` — valid reads pass, writes rejected, injection attempts rejected, CALL db.labels() passes, CALL{} rejected, case-insensitive

**Verify:** `pytest tests/unit/test_cypher_sanitiser.py -x -v`

### Run 2.2: Neo4j Service + Guardrails
- `backend/app/services/__init__.py`
- `backend/app/services/neo4j_service.py` — per §14.5: connect (5 retries, exp backoff, 30s max), close, is_connected, get_schema (asyncio.gather for counts, 10s timeout), get_samples, get_relationship_samples, search, expand, find_paths, execute_raw. All queries via `session.execute_read()`. Element IDs via `node.element_id`. Pool max 10.
- `backend/app/services/guardrails.py` — per §14.4: HARD_LIMITS dict, check_expansion (current + requested vs 500, warning at 400+), check_hops, resolve_effective_limit. Returns GuardrailResult dataclass.

**Verify:** import check

### Run 2.3: Wire Neo4j + Guardrail Tests
- `backend/app/dependencies.py` — add `get_neo4j()` from `app.state`, raises 503 if not connected
- `backend/app/main.py` — update lifespan: Neo4j connect attempt after Alembic, degraded mode on failure, `/health` returns neo4j status
- `backend/tests/unit/test_guardrails.py` — expansion at 490+20 rejects, 480+20 passes, 395+10 passes with warning, hops clamped, resolve_effective_limit picks min
- `backend/tests/unit/conftest.py` — shared fixtures

**Verify:** `pytest tests/unit/test_guardrails.py -x -v`, health check shows neo4j status

---

## Stage 3 — Session Lifecycle (3 runs)

### Run 3.1: Schemas + Session/Finding Services
- `backend/app/models/schemas.py` — ALL schemas from §14.3: GraphNode, GraphEdge, CanvasState, SessionCreate, SessionUpdate, SessionResponse, FindingCreate, FindingResponse, SearchRequest/Response, ExpandRequest/Response, PathRequest/Response, SchemaResponse, LabelInfo, RelTypeInfo, RawQueryRequest
- `backend/app/services/session_service.py` — create, get, get_last_active, update, delete, reset (clears canvas, keeps findings), list_all
- `backend/app/services/finding_service.py` — CRUD, snapshot as BLOB, has_snapshot computed

**Verify:** import check

### Run 3.2: Action Logger + Routers
- `backend/app/services/action_log.py` — dual-sink (NDJSON file + SQLite), fire-and-forget via BackgroundTasks
- `backend/app/routers/__init__.py`
- `backend/app/routers/sessions.py` — POST /sessions, GET /sessions/last-active (BEFORE /{id}!), GET /{id}, PUT /{id}, DELETE /{id}, POST /{id}/reset. Export/import as 501 stubs. All envelope-wrapped.
- `backend/app/routers/findings.py` — GET/POST/PUT/DELETE findings. All envelope-wrapped.

**Verify:** import check

### Run 3.3: Wire Routers + API Tests
- `backend/app/main.py` — include session + finding routers
- `backend/tests/api/conftest.py` — httpx.AsyncClient + ASGITransport, test DB setup, dependency overrides
- `backend/tests/api/test_session_endpoints.py` — create 201, get 200, update, delete, reset preserves findings, last-active
- `backend/tests/unit/test_session_service.py` — service-level tests with in-memory SQLite

**Verify:** `pytest tests/api/test_session_endpoints.py -x -v`

---

## Stage 4 — Graph Operations (2 runs)

### Run 4.1: Graph Router
- `backend/app/routers/graph.py` — GET /graph/schema, GET /graph/schema/samples/{label}, GET /graph/schema/samples/rel/{type}, POST /graph/search, POST /graph/expand, POST /graph/paths, POST /graph/query. Pattern: validate → guardrail pre-check → service call → envelope. 409 on guardrail violation, 504 on timeout, 400 on sanitiser rejection.
- `backend/app/main.py` — include graph router
- `backend/app/services/guardrails.py` — update: resolve_expansion_limits reads preset config

**Verify:** import check

### Run 4.2: Graph API Tests
- `backend/tests/api/test_graph_endpoints.py` — mocked Neo4jService: search returns envelope, expand at capacity returns 409 with detail, expand with room returns 200, hops clamped, paths work, schema returns labels/types, raw query valid passes, raw query write rejects 400
- `backend/tests/unit/test_neo4j_service.py` — helper method tests with mocked driver
- `backend/tests/fixtures/seed_graph.cypher` — ~50 nodes (Person, Company, Address), ~80 rels (WORKS_AT, OWNS, LOCATED_AT, KNOWS)

**Verify:** `pytest tests/ -x -v` (all tests pass)

---

## Stage 5 — Frontend Shell (5 runs)

### Run 5.1: Vite Scaffold + Types + API Client
- `frontend/package.json` — react, zustand, tailwindcss, cytoscape, cytoscape-cose-bilkent, react-resizable-panels, lucide-react + dev deps
- `frontend/vite.config.ts` — React plugin, proxy /api → localhost:8000
- `frontend/tsconfig.json` — strict, `@/` path alias
- `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, `frontend/src/index.css` — Tailwind setup
- `frontend/src/lib/types.ts` — all TS interfaces from §14.2, must match backend schemas
- `frontend/src/lib/constants.ts` — hard limits, defaults, warning thresholds
- `frontend/src/api/client.ts` — fetch wrapper: get/post/put/delete, envelope unwrap, typed errors

**Verify:** `npm install && npx tsc --noEmit`

### Run 5.2: API Modules + Store Slices
- `frontend/src/api/sessions.ts` — createSession, getSession, getLastActive, updateSession, deleteSession, resetSession
- `frontend/src/api/graph.ts` — getSchema, getSamples, getRelSamples, search, expand, findPaths, rawQuery
- `frontend/src/api/findings.ts` — listFindings, createFinding, updateFinding, deleteFinding
- `frontend/src/store/graphSlice.ts` — nodes, edges, positions, filters + actions (addNodes deduplicates)
- `frontend/src/store/sessionSlice.ts` — session, findings + actions
- `frontend/src/store/uiSlice.ts` — selectedIds, panelStates, banners + actions

**Verify:** `npx tsc --noEmit`

### Run 5.3: Config Slice + Store Index + Session Restore
- `frontend/src/store/configSlice.ts` — activePreset (standard default), presetConfig (hops, expansionLimit)
- `frontend/src/store/index.ts` — combine all slices with `create<AllSlices>()`
- `frontend/src/hooks/useSessionRestore.ts` — on mount: getLastActive → populate session + graph slices
- `frontend/tests/store.test.ts` — addNodes dedup, setFilters, setPreset, banners, session set/clear

**Verify:** `npm test -- --run`

### Run 5.4: Layout Components
- Init shadcn/ui: `npx shadcn@latest init` + add button, input, tabs, scroll-area, dialog, dropdown-menu, toast, badge, separator
- `frontend/src/components/layout/Toolbar.tsx` — session name, preset selector, Neo4j status dot
- `frontend/src/components/layout/MainLayout.tsx` — 3-column with react-resizable-panels (Navigator 20%, Canvas fill, Inspector 20% collapsible)
- `frontend/src/components/navigator/Navigator.tsx` — tab container (Search, Filters, Findings, Database)
- `frontend/src/components/navigator/SearchPanel.tsx` — search input + results list, add-to-canvas button
- `frontend/src/components/navigator/FilterPanel.tsx` — label/type toggles from canvas state
- `frontend/src/components/inspector/Inspector.tsx` — reads selectedIds, renders NodeDetail or EdgeDetail

**Verify:** `npx tsc --noEmit`, visual check in dev server

### Run 5.5: Detail Components + Remaining Panels + Docker
- `frontend/src/components/inspector/NodeDetail.tsx` — labels, properties table, expand button (disabled until Stage 6)
- `frontend/src/components/inspector/EdgeDetail.tsx` — type, source/target, properties table
- `frontend/src/components/navigator/FindingsPanel.tsx` — list findings, basic "Add Finding" dialog (title + body)
- `frontend/src/components/navigator/DatabaseOverview.tsx` — schema labels/types with counts, "View Samples" expansion
- `frontend/src/App.tsx` — Toolbar + MainLayout with Navigator/canvas placeholder/Inspector, useSessionRestore
- `frontend/src/main.tsx` — React root render
- `frontend/Dockerfile` — multi-stage Node 20 build + nginx serve with /api proxy
- `docker-compose.yml` — add frontend service at 127.0.0.1:5173

**Verify:** `npm run build`, `docker compose up --build`

---

## Stage 6 — Canvas Integration (4 runs)

### Run 6.1: Cytoscape Setup + Sync Hook
- `frontend/src/lib/cytoscape.ts` — createCytoscapeInstance, layout configs (CoSE-Bilkent default, concentric, breadthfirst), runLayout helper
- `frontend/src/components/canvas/cytoscapeStyles.ts` — node styles (shape by label, color, selection border), edge styles (type label, bezier, arrow), .ghost class
- `frontend/src/components/canvas/useCanvasSync.ts` — inbound sync (store → cy diff, batched add/remove, layout after), outbound (debounced 200ms position writeback), selection (tap → uiSlice.selectedIds), filter application (hide/show by label/type)

**Verify:** `npx tsc --noEmit`

### Run 6.2: Canvas Component + Banners
- `frontend/src/components/canvas/CytoscapeCanvas.tsx` — mount cy into div ref, useEffect create/destroy, apply styles, attach sync hook, ResizeObserver for panel resize
- `frontend/src/components/canvas/CanvasBanners.tsx` — absolute overlay, warning at 400+ nodes, error at 500, dismissible, pointer-events handling
- `frontend/src/App.tsx` — replace canvas placeholder with CytoscapeCanvas + CanvasBanners

**Verify:** dev server shows canvas, manual node add via devtools

### Run 6.3: Graph Actions + Panel Wiring
- `frontend/src/hooks/useGraphActions.ts` — searchAndSeed, expandNode (sends current_canvas_count, handles 409 → banner), findPaths. Bridge between UI and API+store.
- `frontend/src/components/navigator/SearchPanel.tsx` — wire to useGraphActions, "Add to canvas" + "Add & Expand" per result
- `frontend/src/components/inspector/NodeDetail.tsx` — wire "Expand" button, hop count selector (1–5), rel type filter
- `frontend/src/components/navigator/FilterPanel.tsx` — wire toggles to graphSlice.setFilters → cy sync

**Verify:** with backend: search → add → expand flow works

### Run 6.4: Inspector Wiring + Schema Display + Tests
- `frontend/src/components/inspector/Inspector.tsx` — subscribe to cy tap via uiSlice.selectedIds, lookup node/edge in graphSlice
- `frontend/src/components/navigator/DatabaseOverview.tsx` — wire to getSchema + getSamples, loading/error states
- `frontend/tests/components/Inspector.test.tsx` — renders placeholder, NodeDetail, EdgeDetail
- `frontend/tests/store.test.ts` — update: graph actions flow tests

**Verify:** `npm test -- --run`, full investigation flow in browser

---

## Stage 7 — Polish & Export (3 runs)

### Run 7.1: Export/Import Backend
- `backend/app/utils/export.py` — pack_session (ZIP: manifest.json, session.json, canvas.json, action_log.ndjson, findings/), unpack_session, validate_manifest (schema_version must be ≤ 1)
- `backend/app/routers/sessions.py` — replace 501 stubs: POST /{id}/export returns StreamingResponse ZIP, POST /sessions/import accepts file upload
- `backend/tests/unit/test_export.py` — pack creates valid ZIP, round-trip preserves data, rejects version > 1
- `backend/tests/api/test_export_endpoints.py` — export returns ZIP, import creates session

**Verify:** `pytest tests/ -x -v`

### Run 7.2: Frontend Polish
- `frontend/src/components/navigator/FindingsPanel.tsx` — enhanced dialog with "Include canvas snapshot" checkbox (cy.png → base64), list with thumbnails
- `frontend/src/components/navigator/DatabaseOverview.tsx` — pagination for sample tables
- `frontend/src/hooks/useReadOnlyMode.ts` — polls /health every 30s, disables actions when neo4j degraded, persistent banner
- `frontend/src/components/layout/Toolbar.tsx` — export button (downloads .g-lab-session), import button (file picker), new session dialog, editable session name
- `frontend/src/App.tsx` — wire useReadOnlyMode

**Verify:** `npx tsc --noEmit`, visual check

### Run 7.3: Action Logging + Final Artifacts
- `backend/app/routers/graph.py` — add background_tasks.add_task(logger.log) for all endpoints
- `backend/app/routers/sessions.py` — action logging for create, reset, export, import
- `backend/app/routers/findings.py` — action logging for create, update, delete
- `docker-compose.yml` — final: health checks, restart policies
- `.env.example` — all Phase 1 vars with descriptions
- `README.md` — quickstart (Docker + Neo4j → docker compose up → browser)

**Verify:** `pytest tests/ -x -v`, `npm test -- --run`, `docker compose up --build`, full E2E manual test

---

## Run Dependency Graph

```
1.1 → 1.2 → 1.3 ─┬─→ 2.1 → 2.2 → 2.3 → 4.1 → 4.2 ─────┐
                   │                                         │
                   └─→ 3.1 → 3.2 → 3.3 → 5.1 → 5.2 → 5.3  │
                                           → 5.4 → 5.5 ─────┤
                                                             │
                   6.1 → 6.2 → 6.3 → 6.4 ←─────────────────┘
                              │
                              ▼
                   7.1 → 7.2 → 7.3
```

**Parallel streams after Stage 1:** Stages 2–4 (backend) and Stages 3+5 (frontend) can run concurrently. Stage 6 merges both streams.

## Commit Convention

Each run commits as: `ph1-stage-N.R: brief description` (e.g., `ph1-stage-1.1: config, enums, and SQLAlchemy models`)

## Total: 23 runs across 7 stages
