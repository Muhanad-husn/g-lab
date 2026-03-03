"""Lightweight in-memory TTL cache.

Designed for single-async-worker deployments (no thread-safety overhead).

Usage::

    from app.core.cache import TTLCache, cached

    settings_cache = TTLCache(default_ttl=3600)
    settings_cache.set("key", value)
    val = settings_cache.get("key")

    schema_cache = TTLCache(default_ttl=300)

    # key_func receives the same (*args, **kwargs) as the wrapped function.
    # Use ``lambda *_: "schema"`` for a static key; use args for parameterised keys.

    @cached(schema_cache, key_func=lambda *_: "schema")
    async def get_schema() -> dict: ...

    sample_cache = TTLCache(default_ttl=300)

    @cached(sample_cache, key_func=lambda label, **__: f"samples:{label}")
    async def get_samples(label: str) -> list: ...
"""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

__all__ = ["TTLCache", "cached"]

_MISSING = object()

T = TypeVar("T")


@dataclass
class _Entry:
    value: Any
    expires_at: float


@dataclass
class TTLCache:
    """Simple key→value store with per-entry TTL based on ``time.monotonic``."""

    default_ttl: float = 300.0
    _store: dict[str, _Entry] = field(default_factory=dict, repr=False)

    # -- public API ----------------------------------------------------------

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """Return cached value or *default*. Lazily evicts expired entries."""
        entry = self._store.get(key)
        if entry is None or entry.expires_at <= time.monotonic():
            # Evict if expired
            self._store.pop(key, None)
            if default is _MISSING:
                return None
            return default
        return entry.value

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        """Store *value* under *key* with an optional per-entry *ttl*."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        self._store[key] = _Entry(
            value=value,
            expires_at=time.monotonic() + effective_ttl,
        )

    def invalidate(self, key: str) -> bool:
        """Remove *key*. Return ``True`` if it existed."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    def has(self, key: str) -> bool:
        """Check whether *key* exists and is not expired."""
        return self.get(key) is not None

    @property
    def size(self) -> int:
        """Return number of entries (including possibly expired ones)."""
        return len(self._store)

    def cleanup(self) -> int:
        """Eagerly evict all expired entries. Return count of evicted items."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired:
            del self._store[k]
        return len(expired)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def cached(
    cache: TTLCache,
    *,
    key_func: Any = None,
    ttl: float | None = None,
) -> Any:
    """Decorator that caches the return value of sync or async functions.

    Parameters
    ----------
    cache:
        The :class:`TTLCache` instance to use.
    key_func:
        A callable that receives the same ``(*args, **kwargs)`` as the wrapped
        function and returns a cache key string.  Use ``lambda *_: "key"`` for
        a static key; use the arguments for parameterised keys, e.g.
        ``lambda label, **__: f"samples:{label}"``.
        Defaults to ``func.__qualname__`` (identical key for every call).
    ttl:
        Per-entry TTL override (seconds). ``None`` → cache default.
    """

    def decorator(func: Any) -> Any:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                key = key_func(*args, **kwargs) if key_func else func.__qualname__
                hit = cache.get(key)
                if hit is not None:
                    return hit
                result = await func(*args, **kwargs)
                cache.set(key, result, ttl=ttl)
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_func(*args, **kwargs) if key_func else func.__qualname__
            hit = cache.get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            cache.set(key, result, ttl=ttl)
            return result

        return sync_wrapper

    return decorator
