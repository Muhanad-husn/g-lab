"""Tests for the guardrail enforcement service."""

from app.services.guardrails import GuardrailResult, GuardrailService

svc = GuardrailService()


# ── check_expansion ──────────────────────────────────────────────


class TestCheckExpansion:
    """Canvas node cap enforcement."""

    def test_expansion_at_capacity_rejected(self) -> None:
        """490 current + 20 requested > 500 → rejected."""
        result = svc.check_expansion(
            current_count=490,
            requested_limit=20,
        )
        assert not result.allowed
        assert result.detail is not None
        assert result.detail["current"] == 490
        assert result.detail["requested"] == 20
        assert result.detail["remaining"] == 10
        assert result.detail["hard_limit"] == 500

    def test_expansion_with_room_allowed(self) -> None:
        """480 current + 20 requested ≤ 500 → allowed."""
        result = svc.check_expansion(
            current_count=480,
            requested_limit=20,
        )
        assert result.allowed
        assert result.detail is None

    def test_expansion_near_threshold_warns(self) -> None:
        """395 + 10 = 405 total; current ≥ 400 → warning."""
        result = svc.check_expansion(
            current_count=400,
            requested_limit=10,
        )
        assert result.allowed
        assert len(result.warnings) == 1
        assert "400" in result.warnings[0]

    def test_expansion_below_threshold_no_warning(self) -> None:
        """300 current → no warning."""
        result = svc.check_expansion(
            current_count=300,
            requested_limit=20,
        )
        assert result.allowed
        assert len(result.warnings) == 0

    def test_expansion_exactly_at_limit(self) -> None:
        """475 + 25 = 500 exactly → allowed."""
        result = svc.check_expansion(
            current_count=475,
            requested_limit=25,
        )
        assert result.allowed

    def test_expansion_one_over_limit(self) -> None:
        """476 + 25 = 501 → rejected."""
        result = svc.check_expansion(
            current_count=476,
            requested_limit=25,
        )
        assert not result.allowed

    def test_expansion_clamped_to_hard_max(self) -> None:
        """Requested 200 but hard max per expansion is 100."""
        result = svc.check_expansion(
            current_count=0,
            requested_limit=200,
        )
        assert result.allowed
        # effective_limit is min(200, 100) = 100

    def test_expansion_preset_limit_used(self) -> None:
        """Preset limit is factored in when below hard max."""
        result = svc.check_expansion(
            current_count=490,
            requested_limit=5,
            preset_limit=5,
        )
        assert result.allowed

    def test_zero_current_large_request(self) -> None:
        """0 nodes, request 100 → allowed."""
        result = svc.check_expansion(
            current_count=0,
            requested_limit=100,
        )
        assert result.allowed


# ── check_hops ───────────────────────────────────────────────────


class TestCheckHops:
    """Hop count validation and clamping."""

    def test_hops_within_limit(self) -> None:
        result = svc.check_hops(requested=3)
        assert result.allowed
        assert result.detail is not None
        assert result.detail["effective_hops"] == 3
        assert len(result.warnings) == 0

    def test_hops_at_max(self) -> None:
        result = svc.check_hops(requested=5)
        assert result.allowed
        assert result.detail is not None
        assert result.detail["effective_hops"] == 5

    def test_hops_clamped_to_max(self) -> None:
        """Requested 10, hard max is 5 → clamped with warning."""
        result = svc.check_hops(requested=10)
        assert result.allowed
        assert result.detail is not None
        assert result.detail["effective_hops"] == 5
        assert len(result.warnings) == 1
        assert "clamped" in result.warnings[0].lower()

    def test_hops_one(self) -> None:
        result = svc.check_hops(requested=1)
        assert result.allowed
        assert result.detail is not None
        assert result.detail["effective_hops"] == 1

    def test_hops_preset_default_used(self) -> None:
        """Preset default 2, requested 2 → effective 2."""
        result = svc.check_hops(
            requested=2, preset_default=2
        )
        assert result.detail is not None
        assert result.detail["effective_hops"] == 2


# ── resolve_effective_limit ──────────────────────────────────────


class TestResolveEffectiveLimit:
    """Limit resolution: requested → preset → hard cap."""

    def test_requested_below_hard_max(self) -> None:
        assert svc.resolve_effective_limit(10, 25, 100) == 10

    def test_requested_above_hard_max(self) -> None:
        assert svc.resolve_effective_limit(200, 25, 100) == 100

    def test_none_uses_preset_default(self) -> None:
        assert svc.resolve_effective_limit(None, 25, 100) == 25

    def test_none_preset_above_hard_max(self) -> None:
        assert svc.resolve_effective_limit(None, 150, 100) == 100

    def test_picks_minimum(self) -> None:
        """Always picks min(value, hard_max)."""
        assert svc.resolve_effective_limit(50, 25, 100) == 50
        assert svc.resolve_effective_limit(50, 25, 30) == 30

    def test_exact_hard_max(self) -> None:
        assert svc.resolve_effective_limit(100, 25, 100) == 100


# ── GuardrailResult dataclass ────────────────────────────────────


class TestGuardrailResult:
    """Verify the dataclass shape."""

    def test_default_warnings_empty(self) -> None:
        r = GuardrailResult(allowed=True)
        assert r.warnings == []
        assert r.detail is None

    def test_with_detail(self) -> None:
        r = GuardrailResult(
            allowed=False,
            detail={"current": 490, "remaining": 10},
        )
        assert not r.allowed
        assert r.detail["remaining"] == 10

    def test_with_warnings(self) -> None:
        r = GuardrailResult(
            allowed=True, warnings=["close to limit"]
        )
        assert r.warnings == ["close to limit"]
