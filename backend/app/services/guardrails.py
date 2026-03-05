"""Guardrail enforcement for graph operations.

Pre-flight checks that run BEFORE any query execution.
Hard limits are non-overridable. Soft limits resolve from
request → session preset → hard limit cap.
"""

from __future__ import annotations

import asyncio
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
        "copilot_timeout_ms": 120_000,
        "max_concurrent_copilot": 1,
        "max_doc_upload_size_mb": 50,
        "max_docs_per_library": 100,
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

    def check_copilot_available(
        self,
        semaphore: asyncio.Semaphore,
    ) -> GuardrailResult:
        """Check whether the copilot semaphore slot is free.

        Returns ``allowed=True`` when the semaphore can be acquired
        immediately (i.e. no copilot request is currently in flight).
        Returns ``allowed=False`` with a detail dict when busy.
        """
        if semaphore.locked():
            return GuardrailResult(
                allowed=False,
                detail={"message": "Copilot is already processing a request"},
            )
        return GuardrailResult(allowed=True)

    def check_doc_upload(
        self,
        file_size_bytes: int,
        library_doc_count: int,
    ) -> GuardrailResult:
        """Check document upload guardrails.

        Args:
            file_size_bytes: Size of the file being uploaded in bytes.
            library_doc_count: Current number of documents in the library.
        """
        max_size_mb = self.HARD_LIMITS["max_doc_upload_size_mb"]
        max_docs = self.HARD_LIMITS["max_docs_per_library"]

        file_size_mb = file_size_bytes / (1024 * 1024)
        if file_size_mb > max_size_mb:
            return GuardrailResult(
                allowed=False,
                detail={
                    "file_size_mb": round(file_size_mb, 2),
                    "hard_limit_mb": max_size_mb,
                },
            )

        if library_doc_count >= max_docs:
            return GuardrailResult(
                allowed=False,
                detail={
                    "current_doc_count": library_doc_count,
                    "hard_limit": max_docs,
                },
            )

        return GuardrailResult(allowed=True)

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
