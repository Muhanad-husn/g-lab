"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.core.logging import configure_logging, get_logger
from app.dependencies import get_settings, set_session_factory
from app.models.db import Base, create_engine, create_session_factory
from app.routers import config_presets as config_presets_router
from app.routers import copilot as copilot_router
from app.routers import documents as documents_router
from app.routers import findings as findings_router
from app.routers import graph as graph_router
from app.routers import sessions as sessions_router
from app.services.action_log import ActionLogger
from app.services.copilot.openrouter import OpenRouterClient
from app.services.documents.chromadb_client import ChromaDBClient
from app.services.documents.embeddings import EmbeddingService
from app.services.documents.reranker import RerankerService
from app.services.neo4j_service import Neo4jService
from app.services.preset_service import PresetService
from app.utils.exceptions import Neo4jConnectionError
from app.utils.response import envelope

logger: Any = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Application startup/shutdown lifecycle."""
    settings: Settings = get_settings()
    configure_logging(log_level=settings.GLAB_LOG_LEVEL)

    # --- SQLite setup ---
    data_dir = settings.GLAB_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "glab.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_engine(db_url)
    session_factory = create_session_factory(engine)
    set_session_factory(session_factory)

    # Create tables (in production, Alembic handles migrations;
    # this ensures tables exist for dev/test without running alembic).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_ready", path=str(db_path))

    app.state.engine = engine
    app.state.db_session_factory = session_factory

    # --- Action logger ---
    app.state.action_logger = ActionLogger(
        data_dir=data_dir,
        session_factory=session_factory,
    )

    # --- Seed system presets ---
    preset_svc = PresetService()
    async with session_factory() as db:
        await preset_svc.seed_system_presets(db)
    logger.info("system_presets_seeded")

    # --- Copilot semaphore (max 1 concurrent request) ---
    app.state.copilot_semaphore = asyncio.Semaphore(1)
    logger.info("copilot_semaphore_ready")

    # --- OpenRouter client (optional — requires API key) ---
    settings_obj: Settings = get_settings()
    if settings_obj.OPENROUTER_API_KEY:
        app.state.openrouter_client = OpenRouterClient(
            api_key=settings_obj.OPENROUTER_API_KEY,
            base_url=settings_obj.OPENROUTER_BASE_URL,
        )
        logger.info("openrouter_client_ready")
    else:
        app.state.openrouter_client = None
        logger.info("openrouter_not_configured")

    # --- ChromaDB client + Embedding service + Reranker (optional) ---
    chromadb_client = ChromaDBClient()
    app.state.chromadb_client = chromadb_client
    embedding_service = EmbeddingService(model_name=settings.EMBEDDING_MODEL)
    app.state.embedding_service = embedding_service
    app.state.reranker_service = RerankerService()

    try:
        await chromadb_client.connect(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
        )
        logger.info("chromadb_ready")
    except Exception as exc:
        logger.warning("chromadb_degraded_mode", error=str(exc))

    # --- Neo4j connection (degraded mode on failure) ---
    neo4j_service = Neo4jService()
    app.state.neo4j_service = neo4j_service

    try:
        await neo4j_service.connect(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
        )
    except Neo4jConnectionError as exc:
        logger.warning(
            "neo4j_degraded_mode",
            error=str(exc),
        )

    yield

    # --- Shutdown ---
    await neo4j_service.close()
    await chromadb_client.close()
    openrouter_client: OpenRouterClient | None = getattr(
        app.state, "openrouter_client", None
    )
    if openrouter_client is not None:
        await openrouter_client.close()
    await engine.dispose()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="G-Lab",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Timing middleware ---
    @app.middleware("http")
    async def timing_middleware(request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Duration-Ms"] = str(duration_ms)
        return response

    # --- Routers ---
    app.include_router(sessions_router.router, prefix="/api/v1/sessions")
    app.include_router(findings_router.router, prefix="/api/v1/sessions")
    app.include_router(graph_router.router, prefix="/api/v1/graph")
    app.include_router(config_presets_router.router, prefix="/api/v1/config")
    app.include_router(copilot_router.router, prefix="/api/v1/copilot")
    app.include_router(documents_router.router, prefix="/api/v1/documents")

    # --- Health endpoint ---
    @app.get("/health")
    @app.get("/api/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        neo4j_svc: Neo4jService | None = getattr(
            request.app.state, "neo4j_service", None
        )
        neo4j_status = (
            "connected" if neo4j_svc and neo4j_svc.is_connected() else "disconnected"
        )
        or_client: OpenRouterClient | None = getattr(
            request.app.state, "openrouter_client", None
        )
        copilot_status = "ready" if or_client is not None else "unconfigured"
        chroma_client: ChromaDBClient | None = getattr(
            request.app.state, "chromadb_client", None
        )
        if chroma_client is None:
            vector_store_status = "unconfigured"
        elif chroma_client.is_connected():
            vector_store_status = "ready"
        else:
            vector_store_status = "degraded"
        return envelope(
            {
                "status": "ok",
                "neo4j": neo4j_status,
                "copilot": copilot_status,
                "vector_store": vector_store_status,
            }
        )

    return app


app = create_app()
