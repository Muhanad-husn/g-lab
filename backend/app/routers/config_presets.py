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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.dependencies import get_action_logger, get_db, get_openrouter, get_settings
from app.models.enums import ActionType
from app.models.schemas import CredentialsStatus, CredentialsUpdate, PresetCreate, PresetUpdate
from app.services.action_log import ActionLogger
from app.services.copilot.openrouter import OpenRouterClient
from app.services.neo4j_service import Neo4jService
from app.services.preset_service import PresetService
from app.utils.exceptions import Neo4jConnectionError
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


# ---------------------------------------------------------------------------
# Credentials (runtime connection settings)
# ---------------------------------------------------------------------------


@router.get("/credentials")
async def get_credentials(request: Request) -> dict[str, Any]:
    """Return current connection settings (password masked)."""
    settings = get_settings()
    neo4j_service: Neo4jService | None = getattr(
        request.app.state, "neo4j_service", None
    )
    openrouter_client: OpenRouterClient | None = getattr(
        request.app.state, "openrouter_client", None
    )
    status = CredentialsStatus(
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password_set=bool(settings.NEO4J_PASSWORD),
        openrouter_api_key_set=bool(settings.OPENROUTER_API_KEY),
        neo4j_connected=neo4j_service is not None and neo4j_service.is_connected(),
        openrouter_configured=openrouter_client is not None,
    )
    return envelope(status.model_dump())


@router.post("/credentials")
async def update_credentials(
    body: CredentialsUpdate,
    request: Request,
) -> dict[str, Any]:
    """Update connection credentials at runtime.

    Reconnects Neo4j if any Neo4j field changed.
    Reinitialises the OpenRouter client if the API key changed.
    Returns the updated connection status.
    """
    settings = get_settings()

    neo4j_service: Neo4jService | None = getattr(
        request.app.state, "neo4j_service", None
    )

    # --- Neo4j reconnect ---
    neo4j_fields_changed = any(
        [body.neo4j_uri, body.neo4j_user, body.neo4j_password]
    )
    neo4j_connected = neo4j_service is not None and neo4j_service.is_connected()

    if neo4j_fields_changed and neo4j_service is not None:
        uri = body.neo4j_uri or settings.NEO4J_URI
        user = body.neo4j_user or settings.NEO4J_USER
        password = body.neo4j_password or settings.NEO4J_PASSWORD

        # Persist to in-process settings so health checks reflect new values
        settings.NEO4J_URI = uri
        settings.NEO4J_USER = user
        if body.neo4j_password:
            settings.NEO4J_PASSWORD = body.neo4j_password

        await neo4j_service.close()
        try:
            await neo4j_service.connect(uri=uri, user=user, password=password)
            neo4j_connected = True
        except Neo4jConnectionError:
            neo4j_connected = False

    # --- OpenRouter reinit ---
    openrouter_configured = getattr(request.app.state, "openrouter_client", None) is not None

    if body.openrouter_api_key is not None:
        settings.OPENROUTER_API_KEY = body.openrouter_api_key
        existing: OpenRouterClient | None = getattr(
            request.app.state, "openrouter_client", None
        )
        if existing is not None:
            await existing.close()
        if body.openrouter_api_key:
            request.app.state.openrouter_client = OpenRouterClient(
                api_key=body.openrouter_api_key,
                base_url=settings.OPENROUTER_BASE_URL,
            )
            openrouter_configured = True
        else:
            request.app.state.openrouter_client = None
            openrouter_configured = False

    status = CredentialsStatus(
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password_set=bool(settings.NEO4J_PASSWORD),
        openrouter_api_key_set=bool(settings.OPENROUTER_API_KEY),
        neo4j_connected=neo4j_connected,
        openrouter_configured=openrouter_configured,
    )
    return envelope(status.model_dump())
