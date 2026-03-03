# Backend Conventions

## File Layout

- Routes in `app/routers/`, services in `app/services/`, models in `app/models/`
- Pydantic `BaseModel` for all request/response schemas (defined in `app/models/schemas.py`)
- Enums in `app/models/enums.py`, SQLAlchemy models in `app/models/db.py`
- Every endpoint returns the envelope: `{ data, warnings, meta }` — use `app/utils/response.py`
- Guardrail checks happen BEFORE query execution, not after — see `app/services/guardrails.py`

## Neo4j Rules

- **Read-only.** Driver configured with `default_access_mode=READ`. Every query uses `session.execute_read()` — never `execute_write()`.
- **Element IDs are strings** like `"4:abc:123"`. Never parse, never cast to int.
- **Connection pool** capped at 10 (`max_connection_pool_size`). Single-user app doesn't need more.
- **Driver lifecycle:** `AsyncGraphDatabase.driver()` in FastAPI lifespan context manager. Connect with retry (5 attempts, exponential backoff, 30s max).
- **Degraded mode:** If Neo4j is unreachable after retries, backend starts anyway. Graph endpoints return `503`. Session restore works in read-only review mode.
- **Cypher sanitiser** (`app/utils/cypher.py`) uses an allowlist. Rejects anything not in: `MATCH`, `RETURN`, `WHERE`, `WITH`, `ORDER BY`, `LIMIT`, `OPTIONAL MATCH`, `UNWIND`, `CALL db.*`, `shortestPath`, `allShortestPaths`.
- **Timeouts:** Every query gets a `timeout` parameter (milliseconds) on the driver's `session.run()`. General limit: 30s. Schema count queries: 10s.
- **Schema count queries can be slow.** Run them concurrently with `asyncio.gather`. Return `None` for timed-out counts — the UI shows "—".

## SQLite Rules

- **WAL mode:** Set `PRAGMA journal_mode=WAL` on engine creation via `event.listen(engine, "connect", set_wal_mode)`.
- **Async:** Use `aiosqlite` adapter with SQLAlchemy async engine.
- **Migrations:** Alembic. Auto-apply `alembic upgrade head` on startup via FastAPI lifespan.
- **Canvas state:** Stored as TEXT (JSON), serialized/deserialized via Pydantic. Don't use SQLite JSON functions — not worth the complexity at this scale.

## Guardrail Rules

- **Pre-flight checks only.** The frontend sends `current_canvas_count` with expand/path requests. The backend validates before executing.
- **Hard limits are non-overridable:** 500 canvas nodes, 5 max hops, 100 nodes per expansion, 30s Cypher timeout.
- **Soft limits** resolve from: request param → session preset → hard limit cap. Use `min(requested, hard_max)`.
- **Rejection response:** `409 Conflict` with detail: `{ requested, remaining, hard_limit, current }`.

## Logging Rules

- **Dual-sink:** Every action logs to both NDJSON file (append-only, per-session) and SQLite `action_log` table.
- **Async fire-and-forget:** Use FastAPI `BackgroundTasks`. Never block the request on logging.
- **NDJSON is the source of truth** for exports. If SQLite write fails, NDJSON still has the record.

## Export/Import

- `.g-lab-session` files are ZIP archives. See ARCHITECTURE.md §6.3 for structure.
- Start `manifest.json` at `schema_version: 1`. On import, reject anything > current supported version.
- Use stdlib `zipfile` — no external dependency needed.

## Testing

```bash
pytest tests/unit/ -x -v                    # fast, no external deps
pytest tests/integration/ -x -v             # needs testcontainers (Neo4j)
pytest tests/api/ -x -v                     # needs running backend
```

Integration tests use a deterministic Neo4j fixture from `tests/fixtures/seed_graph.cypher` (~50 nodes, ~80 relationships, 3–4 labels).

## Lint

```bash
ruff check app/ --fix && ruff format app/   # lint + format
mypy app/                                    # type check (strict mode)
```
