G-Lab — STRUCTURE_PH2.md
=========================

> **Status:** v1.0 — March 2026
> **Ownership:** This document defines _where_ to start and _in what order_ to build Phase 2. `PRODUCT.md` defines what and why. `ARCHITECTURE.md` defines how and holds all canonical schemas (§14). `IMPLEMENTATION_PLAN_PH2.md` holds granular per-run file lists and verify steps.
> **Scope:** Phase 2 only. Phase 1 (Stages 1–7) is complete.

* * *

## 1. Build Order

Build proceeds in **5 stages** (Stages 8–12, continuing from Phase 1). Each stage produces a runnable or testable increment. Dependencies flow downward — never start a stage until its prerequisites are done.

```
Stage 8: Copilot Infrastructure (OpenRouter, crypto, presets)
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
Stage 9: Copilot Pipeline       Stage 11: Frontend Copilot
  (router, retrieval,              (slices, SSE hook,
   synthesiser, orchestrator)       panel, delta preview)
    │                                  │
    ▼                                  │
Stage 10: Copilot API                  │
  (SSE endpoint, conversation          │
   storage, API tests)                 │
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
             Stage 12: Integration & Polish
```

**Parallel work streams:**

- **Stream A (backend pipeline):** Stages 9–10. Full copilot backend without touching React.
- **Stream B (frontend):** Stage 11 starts when Stage 8 is done (needs schemas + types). Mock SSE data.
- **Stream C (presets API):** Run 8.3 can proceed in parallel with Stage 9.
- **Merge:** Stage 12 requires all three streams complete.

* * *

### Stage 8 — Copilot Infrastructure

**Goal:** OpenRouter client works, API key encryption in place, presets CRUD operational, system presets seeded.

**Depends on:** Phase 1 complete.

**Runs:** 3

**Files:**

1. `backend/app/services/copilot/openrouter.py` — Async httpx client for OpenRouter: chat completion (streaming + non-streaming), model listing, 429 retry with backoff
2. `backend/app/utils/crypto.py` — Fernet encryption for API key at rest, machine-specific seed via PBKDF2
3. `backend/app/config.py` — Extend Settings with `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`
4. `backend/alembic/versions/002_add_presets_and_conversations.py` — `presets` + `conversation_messages` tables
5. `backend/app/models/db.py` — `Preset` and `ConversationMessage` ORM models
6. `backend/app/models/schemas.py` — Phase 2 schemas: `PresetConfig`, `PresetCreate/Update/Response`, `CopilotQueryRequest`, `RouterIntent`, `ConfidenceScore`, `GraphDelta`, `EvidenceSource`, `CopilotMessage`
7. `backend/app/services/preset_service.py` — CRUD + system preset seeding (Quick Scan, Standard Investigation, Deep Dive)
8. `backend/app/routers/config_presets.py` — Preset CRUD endpoints + `GET /config/models`. System presets immutable (403).
9. `backend/app/dependencies.py` — `get_openrouter` dependency
10. `backend/app/main.py` — Wire config router, seed presets in lifespan, health reports copilot status

**Test:** `pytest tests/unit/test_openrouter.py tests/unit/test_crypto.py tests/unit/test_preset_service.py`, `pytest tests/api/test_preset_endpoints.py`

**Acceptance:** `GET /config/presets` returns 3 system presets. User preset CRUD works. `GET /config/models` returns model list (mocked in tests).

* * *

### Stage 9 — Copilot Pipeline

**Goal:** Three-role pipeline (Router → Graph Retrieval → Synthesiser) works end-to-end in isolation. Re-retrieval on low confidence. SSE event assembly.

**Depends on:** Stage 8 (OpenRouter client).

**Runs:** 4

**Files:**

1. `backend/app/services/copilot/prompts.py` — All prompt templates: `ROUTER_SYSTEM_PROMPT`, `GRAPH_RETRIEVAL_SYSTEM_PROMPT`, `SYNTHESISER_SYSTEM_PROMPT`
2. `backend/app/services/copilot/router.py` — `RouterService.classify()` — intent classification via lightweight model. JSON structured output → `RouterIntent`.
3. `backend/app/services/copilot/graph_retrieval.py` — `GraphRetrievalService.retrieve()` — Cypher generation, sanitiser pass-through (retry once on rejection), execution via `neo4j_service.execute_raw()`
4. `backend/app/services/copilot/synthesiser.py` — `SynthesiserService.synthesise()` — answer composition with confidence scoring, streams SSE events
5. `backend/app/services/copilot/sse.py` — `SSEEvent` dataclass, `format_sse()`, `parse_openrouter_stream()`
6. `backend/app/services/copilot/pipeline.py` — `CopilotPipeline.execute()` — orchestrates full flow with status events, re-retrieval on low confidence, `asyncio.wait_for(120s)`, `asyncio.Semaphore(1)`
7. `backend/app/services/guardrails.py` — Extend: `COPILOT_TIMEOUT_MS`, `MAX_CONCURRENT_COPILOT`, `check_copilot_available()`

**Test:** Unit tests per service (mocked OpenRouter + Neo4j): intent classification, Cypher gen + retry, streaming output, pipeline orchestration, re-retrieval flow, timeout, semaphore.

**Acceptance:** `CopilotPipeline.execute()` yields correctly ordered SSE events for a mocked query. Low-confidence triggers one re-retrieval cycle.

* * *

### Stage 10 — Copilot API

**Goal:** SSE streaming endpoint live. Conversation history persisted and retrievable. Guardrails enforced at API level.

**Depends on:** Stage 9 (pipeline).

**Runs:** 2

**Files:**

1. `backend/app/routers/copilot.py` — `POST /copilot/query` (StreamingResponse, SSE), `GET /copilot/history/{session_id}`
2. `backend/app/services/conversation_service.py` — `save_message()`, `get_history()`, `clear_history()`
3. `backend/app/dependencies.py` — `get_copilot_semaphore`
4. `backend/app/main.py` — Wire copilot router, store semaphore on `app.state`

**Test:** `pytest tests/api/test_copilot_endpoints.py` — SSE format, history retrieval, 503 when unconfigured, 409 on concurrent request, conversation stored after stream.

**Acceptance:** `POST /copilot/query` streams SSE events. `GET /copilot/history/{session_id}` returns conversation. Concurrent request returns 409.

* * *

### Stage 11 — Frontend Copilot

**Goal:** CopilotPanel renders at bottom, consumes SSE stream, shows ghost elements on canvas, user can accept/discard deltas.

**Depends on:** Stage 8 (schemas/types). Can proceed in parallel with Stages 9–10 using mock SSE data.

**Runs:** 3

**Files:**

1. `frontend/src/lib/types.ts` — Phase 2 types: `CopilotQueryRequest`, `CopilotMessage`, `ConfidenceScore`, `GraphDelta`, `EvidenceSource`, `SSEEvent`, `PresetResponse`, `PresetConfig`, `ModelInfo`
2. `frontend/src/api/copilot.ts` — POST-based SSE streaming via fetch, `getHistory()`
3. `frontend/src/api/config.ts` — Preset CRUD callers, `getModels()`
4. `frontend/src/store/copilotSlice.ts` — Streaming state, pendingDelta, confidence, evidence, `acceptDelta()` (cross-slice merge into graphSlice)
5. `frontend/src/store/configSlice.ts` — Expand: `advancedMode`, `modelAssignments`, preset list + CRUD actions
6. `frontend/src/hooks/useSSE.ts` — POST-based SSE consumption hook (fetch + line parser, typed event handlers, abort)
7. `frontend/src/components/copilot/CopilotPanel.tsx` — Collapsible bottom panel: chat input, streaming response, pipeline status indicator
8. `frontend/src/components/copilot/ConfidenceBadge.tsx` — Green/yellow/red pill by confidence band
9. `frontend/src/components/copilot/EvidencePanel.tsx` — Evidence source list in Inspector, clickable IDs → canvas selection
10. `frontend/src/components/copilot/DeltaPreview.tsx` — Accept/Discard bar when pendingDelta present
11. `frontend/src/components/canvas/useCanvasSync.ts` — Update: sync pendingDelta as ghost elements, clear on discard, promote on accept
12. `frontend/src/components/layout/MainLayout.tsx` — Add bottom panel slot for CopilotPanel

**Test:** `copilotSlice.test.ts` (stream lifecycle, cross-slice acceptDelta), `CopilotPanel.test.tsx` (renders, submits, streams).

**Acceptance:** CopilotPanel opens at bottom, query submission shows streaming text, ghost nodes appear on canvas, Accept merges them, Discard removes them.

* * *

### Stage 12 — Integration & Polish

**Goal:** Full investigation flow with Copilot. Advanced mode UI. Action logging. Docker ready.

**Depends on:** Stages 10 + 11.

**Runs:** 2

**Files:**

1. `frontend/src/components/layout/Toolbar.tsx` — Copilot status indicator, Advanced Mode toggle, model dropdowns, temperature sliders, preset management
2. `frontend/src/components/navigator/Navigator.tsx` — "Copilot" tab (conversation history view)
3. `frontend/src/components/inspector/Inspector.tsx` — EvidencePanel tab when evidence available
4. `frontend/src/hooks/usePresetRestore.ts` — Load presets on mount, sync changes to session
5. `backend/app/routers/copilot.py` — Action logging: `copilot_query` with payload + result_summary
6. `backend/app/routers/config_presets.py` — Action logging: `preset_create/update/delete`
7. `backend/pyproject.toml` — Promote `httpx` to main deps, add `cryptography`
8. `docker-compose.yml` — `OPENROUTER_API_KEY` + `OPENROUTER_BASE_URL` env passthrough
9. `.env.example` — Phase 2 vars with descriptions
10. `README.md` — Phase 2 section (Copilot setup, OpenRouter key, presets, advanced mode)

**Test:** Full backend suite + full frontend suite. `docker compose up --build`. Manual E2E: configure OpenRouter key → ask a question → see streaming response → accept delta → nodes on canvas.

**Acceptance:** Phase 2 validation criteria met — Copilot demonstrably reduces time-to-insight on an investigation compared to Phase 1 alone.

* * *

## 2. Phase 1 Infrastructure Reused

Phase 2 builds on — but does not restructure — these Phase 1 components:

| Phase 1 Component               | Phase 2 Usage                                          |
| -------------------------------- | ------------------------------------------------------ |
| `app/utils/cypher.py`            | Sanitises LLM-generated Cypher (same allowlist)        |
| `app/services/guardrails.py`     | Extended with copilot timeout + concurrent limit       |
| `app/services/neo4j_service.py`  | `execute_raw()` runs generated queries                 |
| `app/services/action_log.py`     | Logs `copilot_query` + preset actions                  |
| `app/core/cache.py`              | `@cached` decorator for model registry (1hr TTL)       |
| `cytoscapeStyles.ts` `.ghost`    | Ghost class for proposed delta nodes/edges             |
| `store/configSlice.ts`           | Expanded with advancedMode + model assignments         |
| `hooks/useGraphActions.ts`       | Pattern reused for `acceptCopilotDelta()`              |

* * *

## 3. Key Design Decisions

| Decision                      | Chosen                       | Rationale                                                         |
| ----------------------------- | ---------------------------- | ----------------------------------------------------------------- |
| LLM orchestration             | Discrete pipeline, not agent | Explicit control, deterministic I/O at each stage, debuggable     |
| Model gateway                 | OpenRouter                   | Single API surface, user model choice, no direct provider lock-in |
| Streaming protocol            | SSE (not WebSocket)          | Simpler, stateless, sufficient for one-way stream                 |
| Graph deltas                  | Ghost elements pending accept| User-driven mutations — Copilot proposes, user disposes           |
| Confidence re-retrieval       | Automatic, one cycle         | Improves accuracy without runaway loops                           |
| Preset architecture           | System immutable + user CRUD | Guides new users, empowers power users                            |
| API key storage               | Fernet encryption at rest    | Prevents casual exposure; not HSM-grade (acceptable for local)    |

* * *

## 4. New Environment Variables

| Variable              | Required | Default                        |
| --------------------- | -------- | ------------------------------ |
| `OPENROUTER_API_KEY`  | Yes      | —                              |
| `OPENROUTER_BASE_URL` | No       | `https://openrouter.ai/api/v1` |

* * *

## 5. Commit Convention

Format: `ph2-stage-N.R: description` (e.g., `ph2-stage-8.1: openrouter client, crypto utils, config extension`)

Progress derived from git history:
```bash
git log --oneline --grep='ph2-stage-'        # all Phase 2 runs
git log --oneline --grep='ph2-stage-N.'      # runs for stage N
```

## Total: 14 runs across 5 stages (Stages 8–12)
