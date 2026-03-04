"""Tests for app.core.cache."""

from __future__ import annotations

import time

from app.core.cache import TTLCache, cached


class TestTTLCacheBasics:
    """Basic get/set/invalidate operations."""

    def test_set_and_get(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_get_missing_returns_none(self) -> None:
        cache = TTLCache()
        assert cache.get("missing") is None

    def test_get_missing_returns_default(self) -> None:
        cache = TTLCache()
        assert cache.get("missing", "fallback") == "fallback"

    def test_set_overwrites(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v1")
        cache.set("k", "v2")
        assert cache.get("k") == "v2"

    def test_invalidate_existing(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        assert cache.invalidate("k") is True
        assert cache.get("k") is None

    def test_invalidate_missing(self) -> None:
        cache = TTLCache()
        assert cache.invalidate("nope") is False

    def test_clear(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_has_existing(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        assert cache.has("k") is True

    def test_has_missing(self) -> None:
        cache = TTLCache()
        assert cache.has("nope") is False

    def test_size(self) -> None:
        cache = TTLCache(default_ttl=60)
        assert cache.size == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size == 2


class TestTTLCacheExpiry:
    """TTL expiration behavior."""

    def test_expired_entry_returns_none(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        # Simulate time passing beyond TTL
        cache._store["k"].expires_at = time.monotonic() - 1
        assert cache.get("k") is None

    def test_expired_entry_returns_default(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        cache._store["k"].expires_at = time.monotonic() - 1
        assert cache.get("k", "fallback") == "fallback"

    def test_expired_entry_evicted_on_get(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        cache._store["k"].expires_at = time.monotonic() - 1
        cache.get("k")
        assert "k" not in cache._store

    def test_has_expired_returns_false(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("k", "v")
        cache._store["k"].expires_at = time.monotonic() - 1
        assert cache.has("k") is False

    def test_custom_ttl_per_entry(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("short", "v", ttl=0.01)
        cache.set("long", "v", ttl=3600)
        time.sleep(0.05)
        assert cache.get("short") is None
        assert cache.get("long") == "v"

    def test_cleanup_evicts_expired(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("alive", "v")
        cache.set("dead1", "v")
        cache.set("dead2", "v")
        now = time.monotonic()
        cache._store["dead1"].expires_at = now - 1
        cache._store["dead2"].expires_at = now - 1
        evicted = cache.cleanup()
        assert evicted == 2
        assert cache.size == 1
        assert cache.has("alive")

    def test_cleanup_returns_zero_when_nothing_expired(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("a", 1)
        assert cache.cleanup() == 0


class TestTTLCacheEdgeCases:
    """Edge cases and data type handling."""

    def test_none_value_cached(self) -> None:
        """None is a valid cached value — uses _MISSING sentinel internally."""
        cache = TTLCache(default_ttl=60)
        cache.set("k", None)
        # has() checks via get() which returns None for both missing and
        # actual None values, so has() returns False for None values.
        # This is a known trade-off documented by the sentinel pattern.
        # Use get() with an explicit default to distinguish.
        assert cache.get("k", "MISSING") is None

    def test_stores_complex_objects(self) -> None:
        cache = TTLCache(default_ttl=60)
        obj = {"nodes": [1, 2], "meta": {"count": 2}}
        cache.set("data", obj)
        assert cache.get("data") == obj

    def test_zero_ttl_expires_immediately(self) -> None:
        cache = TTLCache(default_ttl=0)
        cache.set("k", "v")
        # With TTL=0, the entry expires at monotonic() + 0 which is
        # essentially now, so it should expire on the next get.
        time.sleep(0.001)
        assert cache.get("k") is None


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    def test_sync_function_cached(self) -> None:
        cache = TTLCache(default_ttl=60)
        call_count = 0

        @cached(cache)
        def compute() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        assert compute() == 42
        assert compute() == 42
        assert call_count == 1

    async def test_async_function_cached(self) -> None:
        cache = TTLCache(default_ttl=60)
        call_count = 0

        @cached(cache)
        async def compute() -> int:
            nonlocal call_count
            call_count += 1
            return 99

        assert await compute() == 99
        assert await compute() == 99
        assert call_count == 1

    def test_custom_key_func(self) -> None:
        cache = TTLCache(default_ttl=60)

        @cached(cache, key_func=lambda *_: "my_key")
        def compute() -> str:
            return "hello"

        compute()
        assert cache.has("my_key")

    def test_default_key_is_qualname(self) -> None:
        cache = TTLCache(default_ttl=60)

        @cached(cache)
        def my_func() -> str:
            return "world"

        my_func()
        assert cache.has(
            "TestCachedDecorator.test_default_key_is_qualname.<locals>.my_func"
        )

    def test_custom_ttl_override(self) -> None:
        cache = TTLCache(default_ttl=3600)

        @cached(cache, ttl=0.01)
        def compute() -> str:
            return "short-lived"

        compute()
        time.sleep(0.05)
        # Should have expired due to short TTL
        key = (
            "TestCachedDecorator.test_custom_ttl_override.<locals>.compute"
        )
        assert not cache.has(key)

    async def test_async_custom_key_func(self) -> None:
        cache = TTLCache(default_ttl=60)

        @cached(cache, key_func=lambda *_: "async_key")
        async def compute() -> int:
            return 7

        assert await compute() == 7
        assert cache.has("async_key")

    def test_cache_invalidation_causes_recompute(self) -> None:
        cache = TTLCache(default_ttl=60)
        call_count = 0

        @cached(cache, key_func=lambda *_: "recomp")
        def compute() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        assert compute() == 1
        cache.invalidate("recomp")
        assert compute() == 2
        assert call_count == 2

    def test_parameterised_key_func_isolates_per_arg(self) -> None:
        """key_func receives (*args, **kwargs) — different args produce different keys."""
        cache = TTLCache(default_ttl=60)
        call_count = 0

        @cached(cache, key_func=lambda label, **__: f"samples:{label}")
        def get_samples(label: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"data-for-{label}"

        assert get_samples("Person") == "data-for-Person"
        assert get_samples("Company") == "data-for-Company"
        assert call_count == 2  # two distinct keys, no cross-contamination

        # Second call for each label hits the cache
        assert get_samples("Person") == "data-for-Person"
        assert get_samples("Company") == "data-for-Company"
        assert call_count == 2

    async def test_async_parameterised_key_func(self) -> None:
        """Async variant of parameterised key_func."""
        cache = TTLCache(default_ttl=60)
        call_count = 0

        @cached(cache, key_func=lambda node_id, **__: f"expand:{node_id}")
        async def expand(node_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{node_id}"

        assert await expand("abc") == "result-abc"
        assert await expand("xyz") == "result-xyz"
        assert call_count == 2

        assert await expand("abc") == "result-abc"
        assert call_count == 2
