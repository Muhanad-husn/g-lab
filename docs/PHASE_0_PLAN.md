# Phase 0: Project Bootstrap & Cross-Cutting Infrastructure

## Context

G-Lab has comprehensive documentation and empty file scaffolding but **zero code**. Git is not initialized. The existing 23-run Phase 1 plan (Stages 1-7) bundles infrastructure setup (pyproject.toml, .gitignore, .env.example) into feature-focused runs. Phase 0 extracts infrastructure into a dedicated pre-stage so that:

1. **Central structured logging** exists from the first line of application code — the architecture only defines action logging (NDJSON+SQLite, Stage 3) but has no application-level logging for startup, errors, request tracing, etc.
2. **A lightweight TTL cache** is available for settings and Neo4j schema caching from Stage 1 onward, avoiding the need to retrofit caching patterns later.
3. Dependencies are installable before any Stage 1 code is written.

**No `requirements.txt` needed** — `pyproject.toml` is the modern standard and is already scaffolded. `pip install -e ".[dev]"` works in the conda `g-lab` environment.

---

## Run 0.1: Repository & Dependencies

**Commit:** `ph0-0.1: repository init, dependencies, and environment config`

### Files

| File | Action | Purpose |
|------|--------|---------|
| `.gitignore` | Populate (exists, 0 bytes) | Python, Node, IDE, OS, .env, SQLite, NDJSON, .g-lab-session |
| `backend/pyproject.toml` | Populate (exists, 0 bytes) | All Phase 1 deps + structlog, tool configs (ruff/mypy/pytest) |
| `.env.example` | Populate (exists, 0 bytes) | Phase 1 vars with descriptions, Phase 2+ vars commented out |

### Commands (after file creation)

```bash
cd D:/g_lab
git init
git remote add origin https://github.com/Muhanad-husn/g-lab
cd backend && pip install -e ".[dev]"
python -c "import fastapi, uvicorn, sqlalchemy, aiosqlite, neo4j, pydantic_settings, alembic, structlog; print('OK')"
```

### Key Decisions

**pyproject.toml dependencies** (pin major only, lock exact in lockfile):
- `fastapi>=0.115,<1`, `uvicorn[standard]>=0.32,<1`
- `sqlalchemy[asyncio]>=2.0,<3`, `aiosqlite>=0.20,<1`
- `neo4j>=5.25,<7`, `pydantic-settings>=2.6,<3`, `alembic>=1.14,<2`
- `structlog>=24.4,<26` (NEW — central logging)
- Dev: `ruff>=0.8,<1`, `mypy>=1.13,<2`, `pytest>=8.3,<9`, `pytest-asyncio>=0.24,<1`, `httpx>=0.27,<1`
- Build system: `hatchling` (lightweight, PEP 517/518 compliant)
- Tool configs: ruff (py312, select E/W/F/I/N/UP/B/SIM/RUF), mypy (strict), pytest (`asyncio_mode = "auto"`)

**.env.example contents:**
```
NEO4J_URI=bolt://localhost:7687    # Required
NEO4J_USER=neo4j                   # Required
NEO4J_PASSWORD=                    # Required
GLAB_DATA_DIR=/data                # SQLite + logs + exports
GLAB_LOG_LEVEL=INFO                # DEBUG/INFO/WARNING/ERROR
# Phase 2+: OPENROUTER_API_KEY, OPENROUTER_BASE_URL, CHROMA_HOST, CHROMA_PORT, EMBEDDING_MODEL
```

---

## Run 0.2: Central Logging & Cache

**Commit:** `ph0-0.2: central structured logging and TTL cache with tests`

### Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/__init__.py` | Create | Package init |
| `backend/app/core/__init__.py` | Create (new dir) | Cross-cutting infrastructure subpackage |
| `backend/app/core/logging.py` | Create | Structured logging via structlog |
| `backend/app/core/cache.py` | Create | In-memory TTL cache |
| `backend/tests/__init__.py` | Create | Test package init |
| `backend/tests/unit/__init__.py` | Create | Unit test package init |
| `backend/tests/unit/conftest.py` | Create | Shared fixtures (tmp_data_dir) |
| `backend/tests/unit/test_logging.py` | Create | 10+ tests for logging module |
| `backend/tests/unit/test_cache.py` | Create | 15+ tests for cache module |

### `app/core/logging.py` — Design

- **`configure_logging(log_level)`** — Call once at startup in `main.py` lifespan
  - JSON output in production (INFO+) for Docker log aggregation
  - Colored console in development (DEBUG) for readability
  - `TimeStamper(fmt="iso", utc=True)` — matches project's ISO-8601 convention
  - `PrintLoggerFactory(file=sys.stderr)` — keeps logs separate from app output
- **`get_logger(name, **initial_context)`** — Factory for bound loggers, used everywhere
- **`bind_request_context(**kwargs)` / `clear_request_context()`** — Request-scoped context via `structlog.contextvars`; middleware binds `request_id`, `method`, `path`

**Usage in Stage 1+ code:**
```python
# main.py lifespan:
configure_logging(log_level=settings.glab_log_level)

# Any module:
logger = get_logger(__name__)
logger.info("connecting to neo4j", uri=uri)

# Middleware:
clear_request_context()
bind_request_context(request_id=str(uuid4()))
```

### `app/core/cache.py` — Design

- **`TTLCache(default_ttl=300)`** — Dataclass with `get/set/invalidate/clear/cleanup/has/size`
  - `time.monotonic()` for reliable TTL (immune to clock drift)
  - Lazy eviction on `get()`, explicit via `cleanup()`
  - No thread-safety overhead (single async worker)
- **`@cached(cache, key_func, ttl)`** — Decorator for both sync and async functions
  - Async: caches resolved value, not coroutine
  - `key_func` for custom cache keys; defaults to `func.__qualname__`

**Usage in Stage 1+ code:**
```python
# dependencies.py — settings cache:
_settings_cache = TTLCache(default_ttl=3600)

# neo4j_service.py — schema cache:
@cached(schema_cache, key_func=lambda: "schema")
async def get_schema(self) -> SchemaResponse: ...
```

### New `core/` Package Rationale

The existing layout has `utils/` (stateless helpers) and `services/` (business logic). `core/` fills a gap for **application infrastructure** — logging config, caching, potentially middleware in the future. This is additive; nothing is moved from the existing structure.

---

## Impact on Stage 1+ Runs

| Existing Run | Change |
|-------------|--------|
| Run 1.1 (config, enums, models) | Skip `pyproject.toml` (exists). Skip `app/__init__.py` (exists). Use `get_logger()` in config.py |
| Run 1.2 (alembic, response, deps) | `get_settings()` can use `TTLCache` instead of `lru_cache` |
| Run 1.3 (main, docker, tests) | Skip `.gitignore` (exists). Skip `tests/__init__.py` + `tests/unit/__init__.py` (exist). Call `configure_logging()` in lifespan. Add request context middleware |
| Run 2.2 (neo4j service) | Use `get_logger()` for connection logging, `@cached` for schema |
| Run 7.3 (.env.example, README) | Skip `.env.example` (exists, already complete) |

---

## Verification

```bash
cd D:/g_lab/backend
pip install -e ".[dev]"
pytest tests/unit/ -x -v             # all logging + cache tests pass
ruff check app/ && ruff format app/  # clean
mypy app/                            # no errors
```

---

## File Inventory: 12 files across 2 runs

**Run 0.1 (3 populated + git init):** `.gitignore`, `backend/pyproject.toml`, `.env.example`

**Run 0.2 (9 created):** `app/__init__.py`, `app/core/__init__.py`, `app/core/logging.py`, `app/core/cache.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/conftest.py`, `tests/unit/test_logging.py`, `tests/unit/test_cache.py`
