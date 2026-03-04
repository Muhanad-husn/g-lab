"""Preset CRUD service.

Manages system and user presets stored in the ``presets`` SQLite table.
System presets (is_system=1) cannot be updated or deleted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Preset
from app.models.schemas import PresetConfig, PresetCreate, PresetResponse, PresetUpdate

# ---------------------------------------------------------------------------
# System preset definitions
# ---------------------------------------------------------------------------

_SYSTEM_PRESETS: list[dict[str, object]] = [
    {
        "id": "preset-standard",
        "name": "Standard Investigation",
        "config": PresetConfig(
            hops=2,
            expansionLimit=25,
            models={
                "router": "anthropic/claude-3-haiku-20240307",
                "graphRetrieval": "anthropic/claude-3-5-sonnet-20241022",
                "synthesiser": "anthropic/claude-sonnet-4-20250514",
            },
            tokenBudgets={
                "router": 256,
                "graphRetrieval": 512,
                "synthesiser": 4096,
            },
        ),
    },
    {
        "id": "preset-quick",
        "name": "Quick Scan",
        "config": PresetConfig(
            hops=1,
            expansionLimit=10,
            models={
                "router": "anthropic/claude-3-haiku-20240307",
                "graphRetrieval": "anthropic/claude-3-haiku-20240307",
                "synthesiser": "anthropic/claude-3-5-sonnet-20241022",
            },
            tokenBudgets={
                "router": 128,
                "graphRetrieval": 256,
                "synthesiser": 2048,
            },
        ),
    },
    {
        "id": "preset-deep",
        "name": "Deep Dive",
        "config": PresetConfig(
            hops=5,
            expansionLimit=50,
            models={
                "router": "anthropic/claude-3-5-sonnet-20241022",
                "graphRetrieval": "anthropic/claude-sonnet-4-20250514",
                "synthesiser": "anthropic/claude-sonnet-4-20250514",
            },
            tokenBudgets={
                "router": 512,
                "graphRetrieval": 1024,
                "synthesiser": 8192,
            },
        ),
    },
]


class PresetService:
    """CRUD operations for presets."""

    async def list_all(self, db: AsyncSession) -> list[PresetResponse]:
        """Return all presets (system first, then user)."""
        result = await db.execute(
            select(Preset).order_by(Preset.is_system.desc(), Preset.name)
        )
        rows = result.scalars().all()
        return [self._to_response(r) for r in rows]

    async def get(self, db: AsyncSession, preset_id: str) -> PresetResponse | None:
        """Get a single preset by ID."""
        row = await db.get(Preset, preset_id)
        if row is None:
            return None
        return self._to_response(row)

    async def create(
        self, db: AsyncSession, data: PresetCreate
    ) -> PresetResponse:
        """Create a new user preset."""
        preset = Preset(
            id=f"preset-{uuid.uuid4().hex[:12]}",
            name=data.name,
            is_system=0,
            config=data.config.model_dump_json(),
        )
        db.add(preset)
        await db.commit()
        await db.refresh(preset)
        return self._to_response(preset)

    async def update(
        self,
        db: AsyncSession,
        preset_id: str,
        data: PresetUpdate,
    ) -> PresetResponse | None:
        """Update a user preset. Returns None if not found, raises if system."""
        row = await db.get(Preset, preset_id)
        if row is None:
            return None
        if row.is_system:
            raise PermissionError("Cannot modify system presets")
        if data.name is not None:
            row.name = data.name
        if data.config is not None:
            row.config = data.config.model_dump_json()
        await db.commit()
        await db.refresh(row)
        return self._to_response(row)

    async def delete(self, db: AsyncSession, preset_id: str) -> bool:
        """Delete a user preset. Returns False if not found, raises if system."""
        row = await db.get(Preset, preset_id)
        if row is None:
            return False
        if row.is_system:
            raise PermissionError("Cannot delete system presets")
        await db.delete(row)
        await db.commit()
        return True

    async def seed_system_presets(self, db: AsyncSession) -> None:
        """Insert system presets if they don't already exist (idempotent)."""
        for preset_def in _SYSTEM_PRESETS:
            existing = await db.get(Preset, str(preset_def["id"]))
            if existing is None:
                config_obj = preset_def["config"]
                assert isinstance(config_obj, PresetConfig)
                preset = Preset(
                    id=str(preset_def["id"]),
                    name=str(preset_def["name"]),
                    is_system=1,
                    config=config_obj.model_dump_json(),
                )
                db.add(preset)
        await db.commit()

    @staticmethod
    def _to_response(row: Preset) -> PresetResponse:
        return PresetResponse(
            id=row.id,
            name=row.name,
            is_system=bool(row.is_system),
            config=PresetConfig.model_validate_json(row.config),
        )
