# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

G-Lab — graph investigation workbench for data journalists and OSINT investigators. Local, session-based, AI-assisted (Phase 2+). Self-hosted via Docker Compose. The codebase is being built incrementally in stages; check `docs/STRUCTURE_PH1.md` for the current build order.

## Tech Stack

| Layer          | Technology                                     |
| -------------- | ---------------------------------------------- |
| Frontend       | React 18 + TypeScript, Vite, Zustand, Tailwind |
| Graph renderer | Cytoscape.js + CoSE-Bilkent layout             |
| UI components  | shadcn/ui                                      |
| Backend        | FastAPI (Python 3.12), Uvicorn (single worker) |
| Graph DB       | Neo4j (user-managed, read-only connection)     |
| Session store  | SQLite (embedded, WAL mode)                    |
| LLM gateway    | OpenRouter (Phase 2)                           |
| Vector store   | ChromaDB (Phase 3)                             |

## Key Commands

```bash
# Backend
cd backend && ruff check app/ --fix && ruff format app/   # lint
cd backend && mypy app/                                     # type check
cd backend && pytest tests/unit/ -x -v                      # unit tests
cd backend && pytest tests/integration/ -x -v               # integration (needs Neo4j)
cd backend && pytest tests/api/ -x -v                       # API tests (httpx)
cd backend && pytest tests/unit/test_foo.py::test_bar -x -v # single test

# Frontend
cd frontend && npx eslint src/ --fix && npx prettier --write src/   # lint
cd frontend && npx tsc --noEmit                                      # type check
cd frontend && npm test -- --run                                     # unit tests
cd frontend && npm test -- --run src/foo.test.ts                     # single test

# Full stack
docker compose up                                    # run
docker compose -f docker-compose.test.yml up         # E2E tests (Playwright)
```

## Custom Slash Commands

- `/stage-start <N>` — Set up context for Stage N: git init (if needed), create/switch to `stage-N` branch, read docs, derive progress from git history, output stage summary with run completion status.
- `/next-run` — Implement the next pending run on the current `stage-N` branch. Reads docs, fetches library docs via Context7, implements files, runs verify step, commits as `ph1-stage-N.R: description`.
- `/stage-end` — Close the current stage: verify all runs complete, run full test suite, update MEMORY.md, merge to main (with confirmation). Does NOT auto-push.
- `/phase_1 <N>` — Implement an entire stage at once (all runs). Prefer `/stage-start` + `/next-run` for run-by-run control.
- `/test` — Detects recently modified code (backend/frontend), runs appropriate linting and tests.
- `/check-contracts` — Compares Pydantic schemas in `backend/app/models/schemas.py` against TypeScript types in `frontend/src/lib/types.ts`, flags mismatches against `docs/ARCHITECTURE.md` section 14.
- `/core-utils [module]` — Quick-reference for `app/core/` utilities (logging, cache, monitoring). Optional arg filters to one module.
- `/update-docs` — Sync project memory and documentation after meaningful work. Enforces no-duplication, MEMORY.md line budget, topic-file offloading, and core-utils freshness.

## Commit Convention

Format: `ph1-stage-N.R: description` (e.g., `ph1-stage-1.1: config, enums, and SQLAlchemy models`)

Progress is derived from git commit history — no progress file. To check progress:
```bash
git log --oneline --grep='ph1-stage-'        # all completed runs
git log --oneline --grep='ph1-stage-N.'      # runs for stage N
```

## Memory Files

Auto-memory is stored at `C:\Users\mou97\.claude\projects\D--g-lab\memory\MEMORY.md` and loaded into every session. Contains stage completion history (decisions, patterns, gotchas). Updated by `/stage-end` and `/update-docs`. Do not duplicate root CLAUDE.md content there. Run `/update-docs` after any session that produces new patterns, gotchas, or conventions.

## Auto-formatting Hooks

Claude Code hooks are configured in `.claude/settings.json`:
- **Python files:** `ruff format` + `ruff check --fix` runs automatically after every edit.
- **TS/TSX files:** `prettier --write` + `eslint --fix` runs automatically after every edit.
- **Bash guard:** Destructive operations (`rm -rf`, `git reset --hard`, `DROP`, `DELETE`, `MERGE`, `CREATE`) are blocked.

## Critical Constraints

- **Neo4j is read-only.** Every Cypher query goes through the sanitiser. Never `CREATE`, `MERGE`, `SET`, `DELETE`, or `REMOVE`.
- **Neo4j element IDs are strings** like `"4:abc:123"`. Never parse them, never assume format. String types everywhere.
- **Cypher sanitiser uses an allowlist.** Only `MATCH`, `RETURN`, `WHERE`, `WITH`, `ORDER BY`, `LIMIT`, `OPTIONAL MATCH`, `UNWIND`, `CALL db.*`, `shortestPath`, `allShortestPaths`.
- **Guardrail checks are pre-flight.** Always check BEFORE query execution, not after. Violations return 409 Conflict.
- **All endpoints return the envelope:** `{ data, warnings, meta }` on success; `{ error: { code, message, detail }, meta }` on failure.
- **Async everywhere** in the backend. Use `await` for all IO. Single-worker Uvicorn handles concurrency via async.
- **Each phase is additive.** No restructuring of prior-phase code when adding new phases.

## API Conventions

- **Prefix:** All endpoints under `/api/v1`.
- **Status codes:** 200 success, 201 created, 400 validation error, 409 guardrail conflict, 422 unprocessable, 504 Neo4j timeout.
- **Guardrail rejection detail:** `{ requested, remaining, hard_limit, current }`.

## Guardrail Limits

| Guardrail               | Hard limit | Soft default |
| ------------------------ | ---------- | ------------ |
| Canvas nodes             | 500        | —            |
| Max hops                 | 5          | 2            |
| Nodes per expansion      | 100        | 25           |
| Cypher timeout           | 30s        | —            |
| Copilot timeout          | 120s       | —            |
| Concurrent Copilot reqs  | 1          | —            |
| Doc upload size          | 50MB       | —            |
| Docs per library         | 100        | —            |

## Architecture Essentials

- **Ports:** Frontend :5173, Backend :8000, ChromaDB :8100 — all bound to `127.0.0.1`.
- **Neo4j is NOT in Docker Compose** — user manages their own instance.
- **Startup:** Backend connects to Neo4j with retry (5 attempts, exponential backoff, 30s max) → degrades gracefully (503 for graph endpoints) → runs Alembic migrations → Frontend fetches `/api/v1/sessions/last-active`.
- **Type contracts:** `docs/ARCHITECTURE.md` section 14 is the single source of truth for all shared types between backend and frontend. Always check it before adding or modifying schemas.
- **Logging:** Dual-sink — NDJSON file (source of truth) + SQLite `action_log` table. Async fire-and-forget via `BackgroundTasks`.
- **Session export:** `.g-lab-session` files are ZIP archives (manifest.json, session.json, canvas.json, action_log.ndjson, findings/).

## Environment Variables

See `docs/ARCHITECTURE.md` §11.3 for the full reference. Phase 1 requires only `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.

## Do NOT Use

| Avoid                             | Use instead                           |
| --------------------------------- | ------------------------------------- |
| LangChain / LlamaIndex            | Plain `httpx` calls to OpenRouter     |
| Redux / MobX                      | Zustand with slice pattern            |
| Axios                             | Native `fetch` with thin wrapper      |
| D3.js for graph                   | Cytoscape.js                          |
| PostgreSQL                        | SQLite with WAL mode                  |
| neomodel / neontology             | Official `neo4j` Python driver        |
| CSS Modules / styled-components   | Tailwind CSS                          |
| `localStorage` / `sessionStorage` | Zustand (in-memory) + API persistence |

## Documentation

| Document                | Read for                                                          |
| ----------------------- | ----------------------------------------------------------------- |
| `docs/PRODUCT.md`       | What G-Lab is, who it's for, UX rules, investigation flow        |
| `docs/ARCHITECTURE.md`  | System design, data models, API surface, type contracts (sec 14) |
| `docs/IMPLEMENTATION_PLAN.md` | Granular 23-run build plan with per-run file lists               |
| `docs/STRUCTURE_PH1.md` | Build order — what to implement in which stage (Phase 1)         |
| `backend/CLAUDE.md`     | Backend conventions, Neo4j rules, SQLite rules, gotchas          |
| `frontend/CLAUDE.md`    | Frontend conventions, Cytoscape sync rules, store patterns       |

## Test Layers

| Layer       | Tool                    | Directory / Config                        |
| ----------- | ----------------------- | ----------------------------------------- |
| Unit (BE)   | pytest                  | `backend/tests/unit/`                     |
| Integration | pytest + testcontainers | `backend/tests/integration/`              |
| API         | pytest + httpx          | `backend/tests/api/`                      |
| Unit (FE)   | Vitest                  | colocated `*.test.ts` files               |
| Component   | Vitest + Testing Library| colocated `*.test.tsx` files               |
| E2E         | Playwright              | `e2e/`                                    |

Integration tests use `backend/tests/fixtures/seed_graph.cypher` (~50 nodes, ~80 relationships).

## MCP Servers

| Server               | When to use                                                      | Install                                                      |
| -------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------ |
| **Context7**         | Before coding with any library — fetches live API docs           | `claude mcp add context7 -- npx -y @upstash/context7-mcp`    |
| **mcp-neo4j-cypher** | Building/testing Neo4j integration — inspect schema, run queries | `pip install mcp-neo4j-cypher`                                |
| **Playwright MCP**   | Writing/debugging E2E tests — see actual browser state           | `claude mcp add playwright -- npx @anthropic/mcp-playwright`  |

Keep total MCP token usage under 20K per session. Disable MCPs you're not actively using.

## Reference Repos

- `neo4j/neo4j-python-driver` — driver lifecycle, async session patterns, timeout config
- `prrao87/neo4j-python-fastapi` — async FastAPI + Neo4j integration, Docker Compose setup
- `cytoscape/cytoscape.js` `/demos` — layout, style, and event patterns
- `pmndrs/zustand` docs — slice pattern, `StateCreator` type, selector subscriptions

## Dependency Philosophy

Use existing, battle-tested libraries (>1K GitHub stars, actively maintained). Generate custom code only for the glue between them. Pin major versions; lock exact versions in lockfiles. Update quarterly unless security requires earlier.
