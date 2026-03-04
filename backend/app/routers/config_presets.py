"""Config / preset endpoints.

All endpoints are prefixed with /api/v1/config (set in main.py).

Routes:
  GET    /config/presets           — list all presets
  POST   /config/presets           — create user preset (201)
  PUT    /config/presets/{id}      — update user preset (403 if system)
  DELETE /config/presets/{id}      — delete user preset (403 if system)
  GET    /config/models            — list OpenRouter models (503 if no key)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.dependencies import get_action_logger, get_db, get_openrouter
from app.models.enums import ActionType
from app.models.schemas import PresetCreate, PresetUpdate
from app.services.action_log import ActionLogger
from app.services.copilot.openrouter import OpenRouterClient
from app.services.preset_service import PresetService
from app.utils.response import envelope

router = APIRouter()
_svc = PresetService()
_logger: Any = get_logger(__name__)

# Presets are global (not session-scoped); use a stable system session ID for logging.
_SYSTEM_SESSION = "system"


# ---------------------------------------------------------------------------
# GET /presets
# ---------------------------------------------------------------------------


@router.get("/presets")
async def list_presets(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all presets (system presets first, then user presets)."""
    presets = await _svc.list_all(db)
    return envelope([p.model_dump() for p in presets])


# ---------------------------------------------------------------------------
# POST /presets
# ---------------------------------------------------------------------------


@router.post("/presets", status_code=201)
async def create_preset(
    body: PresetCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Create a new user preset."""
    preset = await _svc.create(db, body)
    _logger.info("preset_created", preset_id=preset.id, name=preset.name)
    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.PRESET_CREATE,
        actor="user",
        payload={"name": preset.name, "preset_id": preset.id},
        result_summary={"is_system": preset.is_system},
    )
    return envelope(preset.model_dump())


# ---------------------------------------------------------------------------
# PUT /presets/{preset_id}
# ---------------------------------------------------------------------------


@router.put("/presets/{preset_id}")
async def update_preset(
    preset_id: str,
    body: PresetUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Update a user preset. Returns 403 if the preset is a system preset."""
    try:
        updated = await _svc.update(db, preset_id, body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    _logger.info("preset_updated", preset_id=preset_id)
    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.PRESET_UPDATE,
        actor="user",
        payload={"preset_id": preset_id, "name": body.name},
        result_summary={"updated": True},
    )
    return envelope(updated.model_dump())


# ---------------------------------------------------------------------------
# DELETE /presets/{preset_id}
# ---------------------------------------------------------------------------


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Delete a user preset. Returns 403 if the preset is a system preset."""
    try:
        deleted = await _svc.delete(db, preset_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")

    _logger.info("preset_deleted", preset_id=preset_id)
    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.PRESET_DELETE,
        actor="user",
        payload={"preset_id": preset_id},
        result_summary={"deleted": True},
    )
    return envelope({"deleted": preset_id})


# ---------------------------------------------------------------------------
# GET /models
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(
    openrouter: OpenRouterClient | None = Depends(get_openrouter),
) -> dict[str, Any]:
    """List available OpenRouter models.

    Returns 503 if no OpenRouter API key is configured.
    """
    if openrouter is None:
        raise HTTPException(
            status_code=503,
            detail="OpenRouter is not configured (OPENROUTER_API_KEY not set)",
        )
    models = await openrouter.list_models()
    return envelope(models)
