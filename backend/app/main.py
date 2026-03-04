"""FastAPI application entry point."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.core.logging import configure_logging, get_logger
from app.dependencies import get_settings, set_session_factory
from app.models.db import Base, create_engine, create_session_factory
from app.services.neo4j_service import Neo4jService
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

    # --- Health endpoint ---
    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        neo4j_svc: Neo4jService | None = getattr(
            request.app.state, "neo4j_service", None
        )
        neo4j_status = (
            "connected"
            if neo4j_svc and neo4j_svc.is_connected()
            else "disconnected"
        )
        return envelope(
            {
                "status": "ok",
                "neo4j": neo4j_status,
            }
        )

    return app


app = create_app()
