# G-Lab Phase 2 — Implementation Plan

## Context

Phase 1 is complete (Stages 1–7, 23 runs). Phase 2 adds the AI Copilot layer on top of the working graph workbench. All Phase 1 infrastructure is reused; no restructuring of prior code.

**Key references:** `docs/ARCHITECTURE.md` §7 (Copilot Pipeline), §5.2 (Phase 2 endpoints), §5.5 (SSE protocol), §6.1 (presets table), §9 (guardrails), §10 (security/crypto). `backend/CLAUDE.md` and `frontend/CLAUDE.md` for coding conventions.

---

## Stage 8 — Copilot Infrastructure (3 runs)

### Run 8.1: OpenRouter Client, Crypto Utils, Config Extension
- `backend/app/services/copilot/__init__.py` — package init
- `backend/app/services/copilot/openrouter.py` — async httpx client: `chat_completion(model, messages, temperature, max_tokens, stream)` returning dict or async iterator of SSE chunks. Retry on 429 (3 attempts, exp backoff). `list_models()` fetches `/models`. `_validate_api_key()`.
- `backend/app/utils/crypto.py` — Fernet encryption for API key at rest: `encrypt_key(plaintext) -> str`, `decrypt_key(ciphertext) -> str`. Key derived from machine-specific seed (hostname + data dir) via PBKDF2.
- `backend/app/config.py` — add `OPENROUTER_API_KEY: str = ""`, `OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"` to Settings
- `backend/tests/unit/test_openrouter.py` — mock httpx: successful completion, stream iteration, 429 retry, invalid key, list_models parsing
- `backend/tests/unit/test_crypto.py` — round-trip encrypt/decrypt, different seeds → different ciphertext

**Verify:** `pytest tests/unit/test_openrouter.py tests/unit/test_crypto.py -x -v`

### Run 8.2: Presets Table, Migration, Schemas, Service
- `backend/alembic/versions/002_add_presets_and_conversations.py` — creates `presets` table (id TEXT PK, name TEXT NOT NULL, is_system INTEGER DEFAULT 0, config TEXT NOT NULL) and `conversation_messages` table (id TEXT PK, session_id TEXT FK, role TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL, metadata TEXT). Index on `conversation_messages(session_id, timestamp)`.
- `backend/app/models/db.py` — add `Preset` and `ConversationMessage` ORM models
- `backend/app/models/enums.py` — add `ActionType` values: `copilot_query`, `preset_create`, `preset_update`, `preset_delete`
- `backend/app/models/schemas.py` — add Phase 2 schemas: `PresetConfig`, `PresetCreate`, `PresetUpdate`, `PresetResponse`, `CopilotQueryRequest`, `CopilotMessage`, `RouterIntent`, `ConfidenceScore`, `GraphDelta`, `EvidenceSource`
- `backend/app/services/preset_service.py` — `list_all()`, `get(id)`, `create(data)`, `update(id, data)`, `delete(id)` (reject if is_system). `seed_system_presets()` inserts Quick Scan / Standard Investigation / Deep Dive if not present.
- `backend/tests/unit/test_preset_service.py` — CRUD, system preset immutability, seed idempotency

**Verify:** `pytest tests/unit/test_preset_service.py -x -v`

### Run 8.3: Preset Router, API Tests, Dependency Wiring
- `backend/app/routers/config_presets.py` — `GET /config/presets`, `POST /config/presets` (201), `PUT /config/presets/{id}` (403 if system), `DELETE /config/presets/{id}` (403 if system), `GET /config/models`. All envelope-wrapped.
- `backend/app/dependencies.py` — add `get_openrouter(request)` from `app.state`, returns None if key empty (copilot endpoints → 503)
- `backend/app/main.py` — include config_presets router at `/api/v1/config`. Lifespan: seed system presets, create OpenRouterClient on `app.state.openrouter_client`. Health reports `copilot` status.
- `backend/tests/api/test_preset_endpoints.py` — list returns 3 system presets, CRUD user preset, delete system → 403, models endpoint (mocked)

**Verify:** `pytest tests/api/test_preset_endpoints.py -x -v`, `pytest tests/ -x -v`

---

## Stage 9 — Copilot Pipeline (4 runs)

### Run 9.1: Router Service (Intent Classification)
- `backend/app/services/copilot/router.py` — `RouterService.classify(query, graph_context_summary, model, temperature, max_tokens) -> RouterIntent`. Builds system prompt with schema summary. Instructs JSON output: `needs_graph`, `needs_docs`, `cypher_hint`, `doc_query`. Falls back to `needs_graph=True` on parse failure.
- `backend/app/services/copilot/prompts.py` — all prompt templates as string constants: `ROUTER_SYSTEM_PROMPT`, `GRAPH_RETRIEVAL_SYSTEM_PROMPT`, `SYNTHESISER_SYSTEM_PROMPT`
- `backend/tests/unit/test_copilot_router.py` — mock OpenRouter: graph-only, docs-only, both, parse failure fallback, empty query

**Verify:** `pytest tests/unit/test_copilot_router.py -x -v`

### Run 9.2: Graph Retrieval Service (Cypher Gen + Sanitiser Retry)
- `backend/app/services/copilot/graph_retrieval.py` — `GraphRetrievalService.retrieve(intent, schema_summary, neo4j_service, model, temperature, max_tokens) -> tuple[list[dict], list[EvidenceSource]]`. Generates Cypher → `CypherSanitiser.sanitise()` → if rejected, retry once with amended prompt → execute via `neo4j_service.execute_raw()` (30s timeout) → map to evidence sources.
- `backend/tests/unit/test_graph_retrieval.py` — mock OpenRouter + Neo4j: success, sanitiser reject + retry success, double rejection → empty, timeout

**Verify:** `pytest tests/unit/test_graph_retrieval.py -x -v`

### Run 9.3: Synthesiser Service (Answer + Confidence + Graph Delta)
- `backend/app/services/copilot/synthesiser.py` — `SynthesiserService.synthesise(query, graph_results, graph_context, model, temperature, max_tokens, stream=True) -> AsyncIterator[SSEEvent]`. Streams: `text_chunk`, `evidence`, `graph_delta`, `confidence`, `done`.
- `backend/app/services/copilot/sse.py` — `SSEEvent` dataclass, `format_sse(event) -> str`, `parse_openrouter_stream(response) -> AsyncIterator[str]`
- `backend/tests/unit/test_synthesiser.py` — text chunks emitted, confidence parsed, graph delta emitted, done at end
- `backend/tests/unit/test_sse.py` — SSEEvent formatting, partial chunk parsing

**Verify:** `pytest tests/unit/test_synthesiser.py tests/unit/test_sse.py -x -v`

### Run 9.4: Pipeline Orchestrator (Wiring + Re-Retrieval + Guardrails)
- `backend/app/services/copilot/pipeline.py` — `CopilotPipeline.execute(request, neo4j_service, openrouter_client, preset_config, session_id) -> AsyncIterator[SSEEvent]`. Orchestrates: `status:routing` → Router → `status:retrieving` → Graph Retrieval → Synthesiser → if confidence < 0.40: `status:re_retrieving` → expand retrieval (hops+1) → re-synthesise. Wrapped in `asyncio.wait_for(120s)`. Protected by `asyncio.Semaphore(1)`.
- `backend/app/services/guardrails.py` — add `COPILOT_TIMEOUT_MS = 120_000`, `MAX_CONCURRENT_COPILOT = 1` to `HARD_LIMITS`. Add `check_copilot_available(semaphore)`.
- `backend/tests/unit/test_pipeline.py` — full flow, re-retrieval on low confidence, timeout → error event, semaphore rejection

**Verify:** `pytest tests/unit/test_pipeline.py -x -v`

---

## Stage 10 — Copilot API (2 runs)

### Run 10.1: Copilot Router + Conversation Storage
- `backend/app/routers/copilot.py` — `POST /copilot/query` → `StreamingResponse(media_type="text/event-stream")`. Acquires semaphore (409 if busy). Calls pipeline. Stores conversation after stream. Logs `copilot_query` action. `GET /copilot/history/{session_id}` → list of `CopilotMessage`.
- `backend/app/services/conversation_service.py` — `save_message()`, `get_history(session_id, limit=50)`, `clear_history(session_id)`
- `backend/app/main.py` — include copilot router at `/api/v1/copilot`. Store semaphore on `app.state.copilot_semaphore`.
- `backend/app/dependencies.py` — add `get_copilot_semaphore(request)`

**Verify:** import check, `pytest tests/unit/ -x -v`

### Run 10.2: Copilot API Tests
- `backend/tests/api/test_copilot_endpoints.py` — SSE stream format, history endpoint, copilot unavailable → 503, concurrent → 409, timeout → error event, conversation stored
- `backend/tests/api/conftest.py` — update: override `get_openrouter`, mock semaphore
- `backend/tests/unit/test_conversation_service.py` — save + retrieve, ordering, clear, limit

**Verify:** `pytest tests/ -x -v` (full backend suite)

---

## Stage 11 — Frontend Copilot (3 runs)

### Run 11.1: Types, API Callers, Store Slices
- `frontend/src/lib/types.ts` — add: `CopilotQueryRequest`, `CopilotMessage`, `RouterIntent`, `ConfidenceScore`, `GraphDelta`, `EvidenceSource`, `SSEEvent`, `PresetResponse`, `PresetConfig`, `PresetCreate`, `PresetUpdate`, `ModelInfo`
- `frontend/src/lib/constants.ts` — add `COPILOT_TIMEOUT_MS`, `CONFIDENCE_BANDS`, `SSE_EVENT_TYPES`
- `frontend/src/api/copilot.ts` — `streamQuery(request)` (POST-based SSE via fetch), `getHistory(sessionId)`
- `frontend/src/api/config.ts` — `getPresets()`, `createPreset()`, `updatePreset()`, `deletePreset()`, `getModels()`
- `frontend/src/store/copilotSlice.ts` — `messages`, `isStreaming`, `pendingDelta`, `confidence`, `evidence`, `pipelineStatus`. Actions: `startStream`, `appendTextChunk`, `setEvidence`, `setPendingDelta`, `setConfidence`, `setStatus`, `finishStream`, `clearPendingDelta`, `acceptDelta` (cross-slice → graphSlice), `addMessage`, `loadHistory`.
- `frontend/src/store/configSlice.ts` — expand: `advancedMode`, `modelAssignments`, `presets[]`, preset CRUD actions
- `frontend/src/store/index.ts` — wire `CopilotSlice`
- `frontend/src/hooks/useSSE.ts` — POST-based SSE hook: `fetch` with `text/event-stream`, parse `event:`/`data:` lines, typed handlers, abort support

**Verify:** `npx tsc --noEmit`

### Run 11.2: CopilotPanel, ConfidenceBadge, EvidencePanel
- `frontend/src/components/copilot/CopilotPanel.tsx` — bottom panel (collapsible). Chat input + message list. Pipeline status indicator. Disabled when streaming or readOnly. Dispatches to copilotSlice per SSE event.
- `frontend/src/components/copilot/ConfidenceBadge.tsx` — pill: green/yellow/red by band. Tooltip with explanation.
- `frontend/src/components/copilot/EvidencePanel.tsx` — in Inspector: lists evidence sources, clickable node/edge IDs → select on canvas
- `frontend/src/components/layout/MainLayout.tsx` — add bottom panel slot for CopilotPanel
- `frontend/src/App.tsx` — wire CopilotPanel, add preset loading on mount

**Verify:** `npx tsc --noEmit`

### Run 11.3: DeltaPreview, Ghost Wiring, Tests
- `frontend/src/components/copilot/DeltaPreview.tsx` — overlay bar when `pendingDelta` non-null. Shows count. "Accept" → `acceptDelta()`. "Discard" → `cy.remove('.ghost')` + `clearPendingDelta()`.
- `frontend/src/components/canvas/useCanvasSync.ts` — update: sync `pendingDelta` → add ghost elements to cy, clear on discard, remove `.ghost` class on accept
- `frontend/src/hooks/useGraphActions.ts` — update: `acceptCopilotDelta()` action
- `frontend/tests/copilot/copilotSlice.test.ts` — stream lifecycle, acceptDelta cross-slice, loadHistory
- `frontend/tests/copilot/CopilotPanel.test.tsx` — renders input, submit sends query, streaming text
- `frontend/tests/store.test.ts` — update: copilotSlice tests

**Verify:** `npm test -- --run`, `npx tsc --noEmit`

---

## Stage 12 — Integration & Polish (2 runs)

### Run 12.1: Full Wiring, Advanced Mode UI, Action Logging
- `frontend/src/components/layout/Toolbar.tsx` — copilot status dot, Advanced Mode toggle, model assignment dropdowns, temperature sliders, preset management UI
- `frontend/src/components/navigator/Navigator.tsx` — add "Copilot" tab (conversation history transcript)
- `frontend/src/components/inspector/Inspector.tsx` — show EvidencePanel tab when evidence available
- `frontend/src/hooks/usePresetRestore.ts` — load presets on mount, sync preset changes to session
- `backend/app/routers/copilot.py` — ensure action logging with payload + result_summary
- `backend/app/routers/config_presets.py` — ensure action logging for preset CRUD

**Verify:** `npx tsc --noEmit`, `pytest tests/ -x -v`

### Run 12.2: Docker, Env, Integration Tests, README
- `backend/pyproject.toml` — add `httpx>=0.27,<1` to main deps, add `cryptography>=43,<44`
- `docker-compose.yml` — add `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` env passthrough
- `.env.example` — add Phase 2 vars with descriptions
- `README.md` — add Phase 2 section (Copilot setup, OpenRouter key, presets, advanced mode)
- `backend/tests/unit/test_full_pipeline_integration.py` — all services mocked: query → route → retrieve → synthesise → stream → store conversation
- `frontend/tests/copilot/integration.test.ts` — simulate SSE event sequence → verify state → acceptDelta → graphSlice updated

**Verify:** `pytest tests/ -x -v`, `npm test -- --run`, `docker compose up --build`, manual E2E

---

## Run Dependency Graph

```
8.1 → 8.2 → 8.3 ──────────────────────────────────────────┐
  │     │                                                    │
  │     └──→ 11.1 → 11.2 → 11.3 ──────────────────────────┤
  │                                                          │
  └──→ 9.1 → 9.2 → 9.3 → 9.4 → 10.1 → 10.2 ─────────────┤
                                                             │
                                                       12.1 → 12.2
```

**Parallel streams after Run 8.2:**
- **Stream A (backend pipeline):** 9.1 → 9.2 → 9.3 → 9.4 → 10.1 → 10.2
- **Stream B (frontend):** 11.1 → 11.2 → 11.3 (starts once 8.2 lands schemas)
- **Stream C (presets API):** 8.3 (parallel with 9.x)
- **Merge:** Stage 12 requires all streams complete.

## Commit Convention

Each run commits as: `ph2-stage-N.R: brief description` (e.g., `ph2-stage-8.1: openrouter client, crypto utils, config extension`)

## Total: 14 runs across 5 stages
