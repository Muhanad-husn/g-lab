Quick-reference for `backend/app/core/` utility modules. Use `/core-utils` for all
modules, or `/core-utils logging`, `/core-utils cache`, `/core-utils monitoring` for
a single section.

If $ARGUMENTS is provided, print ONLY the matching section below. Otherwise print all three.

---

## 1. `app.core.logging`

**Import:** `from app.core.logging import configure_logging, get_logger, bind_request_context, clear_request_context, unbind_request_context`

### Public API

| Function | Signature | When to call |
|---|---|---|
| `configure_logging` | `(log_level: str = "INFO") -> None` | Once at app startup (lifespan). DEBUG = coloured console; INFO+ = JSON lines. |
| `get_logger` | `(name: str, **initial_context) -> Any` | Module-level or `__init__`. Returns a structlog bound logger. |
| `bind_request_context` | `(**kwargs) -> None` | Request middleware — binds `request_id`, `session_id`, etc. to contextvars. |
| `clear_request_context` | `() -> None` | Start of every request — wipes all contextvars. |
| `unbind_request_context` | `(*keys: str) -> None` | After a pipeline stage — removes specific keys without wiping the whole context. |

### Usage Patterns

**Module-level logger:**
```python
from app.core.logging import get_logger

logger = get_logger(__name__)

async def do_work():
    logger.info("starting", item_count=42)
```

**Request middleware context:**
```python
from app.core.logging import clear_request_context, bind_request_context

async def request_middleware(request, call_next):
    clear_request_context()
    bind_request_context(request_id=rid, method=request.method, path=request.url.path)
    response = await call_next(request)
    return response
```

**Pipeline stage bind/unbind (Phase 2+):**
```python
from app.core.logging import bind_request_context, unbind_request_context

bind_request_context(pipeline_stage="router", model="claude-haiku-4-5")
# ... all log entries carry pipeline_stage + model ...
unbind_request_context("pipeline_stage", "model")
# request_id / session_id still bound
```

### Gotchas

- `get_logger()` return type is `Any` — `structlog.FilteringBoundLogger` is runtime-generated, not valid for mypy.
- `configure_logging` must be called before any `get_logger()` call for processors to take effect.
- `structlog.get_level_from_name()` was removed in structlog v25+; `make_filtering_bound_logger()` accepts a string level directly.

---

## 2. `app.core.cache`

**Import:** `from app.core.cache import TTLCache, cached`

### Public API

| Symbol | Signature | When to call |
|---|---|---|
| `TTLCache` | `(default_ttl: float = 300.0)` | Instantiate at module level for each cache domain. |
| `.get` | `(key: str, default=None) -> Any` | Read; lazily evicts expired entries. Returns `None` if missing/expired. |
| `.set` | `(key: str, value, *, ttl: float | None = None)` | Write; optional per-entry TTL override. |
| `.invalidate` | `(key: str) -> bool` | Remove one key. Returns `True` if it existed. |
| `.clear` | `() -> None` | Remove all entries. |
| `.has` | `(key: str) -> bool` | Check existence (not expired). |
| `.size` | property `-> int` | Entry count (may include expired). |
| `.cleanup` | `() -> int` | Eagerly evict all expired; returns eviction count. |
| `@cached` | `(cache, *, key_func=None, ttl=None)` | Decorator for sync or async functions. |

### Usage Patterns

**Static-key cache (singleton result):**
```python
from app.core.cache import TTLCache, cached

schema_cache = TTLCache(default_ttl=300)

@cached(schema_cache, key_func=lambda *_: "schema")
async def get_schema() -> dict:
    ...
```

**Parameterised-key cache:**
```python
sample_cache = TTLCache(default_ttl=300)

@cached(sample_cache, key_func=lambda label, **__: f"samples:{label}")
async def get_samples(label: str) -> list:
    ...
```

**Manual get/set (when decorator doesn't fit):**
```python
settings_cache = TTLCache(default_ttl=3600)

async def get_setting(key: str) -> str:
    hit = settings_cache.get(key)
    if hit is not None:
        return hit
    value = await fetch_from_db(key)
    settings_cache.set(key, value)
    return value
```

### Gotchas

- `key_func` receives the same `(*args, **kwargs)` as the wrapped function. Use `lambda *_: "key"` for static, `lambda arg, **__: f"prefix:{arg}"` for parameterised.
- The `@cached` decorator returns `None` cache misses as hits — don't cache functions that legitimately return `None`.
- Windows timer resolution is ~15ms; in tests use `>=10ms` TTL and `>=50ms` sleep for expiry assertions.
- Single-worker async — no locking needed, but also no protection against thundering herd on cold start.

---

## 3. `app.core.monitoring`

**Import:** `from app.core.monitoring import OperationTimer, WarningCollector, Neo4jStatus, Neo4jStatusTracker`

### Public API

| Symbol | Signature | When to call |
|---|---|---|
| `OperationTimer` | `(operation: str, *, logger=None, **metadata)` | `async with` in service methods that need timing + structured logs. |
| `.set_result` | `(**kwargs) -> None` | Inside the `async with` block — attach result metadata to the `op.complete` event. |
| `.duration_ms` | property `-> float` | Read elapsed time mid-operation (e.g. for timeout checks). |
| `WarningCollector.add` | `(message: str) -> None` (static) | Anywhere — guardrails, services, middleware. Adds to request-scoped list. |
| `WarningCollector.get_all` | `() -> list[str]` (static) | Response middleware — read all warnings for the envelope. |
| `WarningCollector.clear` | `() -> None` (static) | Request start — reset for new request. |
| `Neo4jStatus` | `StrEnum: CONNECTED, DEGRADED, DISCONNECTED` | State values for the tracker. |
| `Neo4jStatusTracker` | `()` | Instantiate once (app-level singleton). |
| `.status` | property `-> Neo4jStatus` | Read current state (for `/health`). |
| `.is_available` | property `-> bool` | Guard graph endpoints — `True` only when `CONNECTED`. |
| `.update` | `(new_status, *, reason="") -> None` | Neo4j service calls on connect/disconnect/error. No-op if already in that state. |

### Usage Patterns

**Timing a Neo4j query:**
```python
from app.core.monitoring import OperationTimer

async def expand_node(self, node_id: str) -> list:
    async with OperationTimer("neo4j.expand", logger=self._log, node_id=node_id) as op:
        result = await self._execute_query(...)
        op.set_result(node_count=len(result))
    return result
# Emits: op.start {operation: "neo4j.expand", node_id: "..."}
# Emits: op.complete {operation: "neo4j.expand", duration_ms: 42.1, node_count: 5, node_id: "..."}
```

**Collecting warnings from guardrails:**
```python
from app.core.monitoring import WarningCollector

def check_canvas_limit(current: int, requested: int, hard_limit: int = 500):
    remaining = hard_limit - current
    if requested > remaining * 0.8:
        WarningCollector.add(f"Approaching canvas limit ({current + requested}/{hard_limit} nodes)")
```

**Request middleware pattern:**
```python
from app.core.monitoring import WarningCollector

async def response_middleware(request, call_next):
    WarningCollector.clear()
    response = await call_next(request)
    warnings = WarningCollector.get_all()
    # inject warnings into response envelope
    return response
```

**Neo4j health tracking:**
```python
from app.core.monitoring import Neo4jStatus, Neo4jStatusTracker

neo4j_status = Neo4jStatusTracker()

async def connect_neo4j():
    try:
        await driver.verify_connectivity()
        neo4j_status.update(Neo4jStatus.CONNECTED, reason="startup")
    except Exception:
        neo4j_status.update(Neo4jStatus.DEGRADED, reason="connection_failed")
```

### Gotchas

- `OperationTimer` does NOT suppress exceptions — they propagate after logging `op.error`.
- `WarningCollector` uses `contextvars` — each asyncio task (= each FastAPI request) gets its own copy. Always call `.clear()` at request start.
- `Neo4jStatusTracker.update()` is a no-op if the status hasn't changed — safe to call repeatedly.
- `OperationTimer` uses `time.monotonic()` — immune to system clock adjustments.
