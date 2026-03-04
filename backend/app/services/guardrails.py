"""Guardrail enforcement for graph operations.

Pre-flight checks that run BEFORE any query execution.
Hard limits are non-overridable. Soft limits resolve from
request → session preset → hard limit cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check."""

    allowed: bool
    warnings: list[str] = field(default_factory=list)
    detail: dict[str, Any] | None = None


class GuardrailService:
    """Stateless guardrail checker."""

    HARD_LIMITS: ClassVar[dict[str, int]] = {
        "max_canvas_nodes": 500,
        "max_hops": 5,
        "max_nodes_per_expansion": 100,
        "cypher_timeout_ms": 30_000,
    }

    # Warning threshold: warn when canvas is at or above this.
    _CANVAS_WARNING_THRESHOLD = 400

    def check_expansion(
        self,
        current_count: int,
        requested_limit: int,
        preset_limit: int = 25,
    ) -> GuardrailResult:
        """Check whether an expansion would exceed the canvas node cap.

        Args:
            current_count: Number of nodes currently on canvas.
            requested_limit: Max nodes the expansion can return.
            preset_limit: Session preset default for expansion limit.
        """
        hard_max = self.HARD_LIMITS["max_canvas_nodes"]
        effective_limit = self.resolve_effective_limit(
            requested_limit,
            preset_limit,
            self.HARD_LIMITS["max_nodes_per_expansion"],
        )
        remaining = hard_max - current_count

        # Would the expansion potentially exceed the cap?
        if effective_limit > remaining:
            return GuardrailResult(
                allowed=False,
                detail={
                    "requested": effective_limit,
                    "remaining": remaining,
                    "hard_limit": hard_max,
                    "current": current_count,
                },
            )

        warnings: list[str] = []
        if current_count >= self._CANVAS_WARNING_THRESHOLD:
            warnings.append(
                f"Canvas has {current_count} nodes "
                f"(limit: {hard_max}). "
                f"Consider filtering before expanding."
            )

        return GuardrailResult(
            allowed=True,
            warnings=warnings,
        )

    def check_hops(
        self,
        requested: int,
        preset_default: int = 2,
    ) -> GuardrailResult:
        """Validate and clamp hop count.

        Returns allowed=True with the clamped value in detail.
        """
        hard_max = self.HARD_LIMITS["max_hops"]
        effective = self.resolve_effective_limit(requested, preset_default, hard_max)

        warnings: list[str] = []
        if requested > hard_max:
            warnings.append(f"Hops clamped from {requested} to {hard_max}")

        return GuardrailResult(
            allowed=True,
            warnings=warnings,
            detail={"effective_hops": effective},
        )

    def resolve_expansion_limits(
        self,
        session_config: dict[str, Any] | None = None,
    ) -> int:
        """Return the effective per-expansion node limit from session config.

        Resolution order: session_config → Standard Investigation default (25)
        → hard_max cap.  Call this to get the preset_limit for check_expansion
        when you have a session context available.
        """
        preset = 25  # Standard Investigation default
        if session_config is not None:
            preset = int(session_config.get("max_nodes_per_expansion", preset))
        return min(preset, self.HARD_LIMITS["max_nodes_per_expansion"])

    @staticmethod
    def resolve_effective_limit(
        requested: int | None,
        preset_default: int,
        hard_max: int,
    ) -> int:
        """Resolve: request param → preset default → hard limit cap.

        Returns min(requested or preset_default, hard_max).
        """
        value = requested if requested is not None else preset_default
        return min(value, hard_max)
