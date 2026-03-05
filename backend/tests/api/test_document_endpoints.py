"""API tests for /api/v1/documents endpoints.

Uses a minimal FastAPI app (no lifespan) with in-memory SQLite and
dependency overrides for get_db, get_action_logger, get_chromadb,
and get_embedding_service.
"""

from __future__ import annotations

import io
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dependencies import (
    get_action_logger,
    get_chromadb,
    get_db,
    get_embedding_service,
)
from app.models.db import Base
from app.routers import documents as documents_router
from app.services.action_log import ActionLogger
from app.services.documents.chromadb_client import ChromaDBClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def _engine() -> AsyncGenerator[Any, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def mock_chromadb() -> ChromaDBClient:
    client = MagicMock(spec=ChromaDBClient)
    client.is_connected.return_value = True
    client.create_collection = AsyncMock()
    client.delete_collection = AsyncMock()
    client.add_documents = AsyncMock()
    client.delete_documents = AsyncMock()
    client.get_collection_count = AsyncMock(return_value=0)
    return client


@pytest.fixture()
async def client(
    _engine: Any, mock_chromadb: ChromaDBClient
) -> AsyncGenerator[AsyncClient, None]:
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _engine, expire_on_commit=False
    )

    with tempfile.TemporaryDirectory(prefix="glab_doc_test_") as tmp:
        data_dir = Path(tmp)
        action_logger = ActionLogger(data_dir=data_dir, session_factory=factory)

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            async with factory() as session:
                yield session

        def override_get_action_logger(_request: Request) -> ActionLogger:
            return action_logger

        def override_get_chromadb(_request: Request) -> ChromaDBClient:
            return mock_chromadb

        def override_get_embedding_service(_request: Request) -> None:
            return None

        test_app = FastAPI()
        test_app.include_router(documents_router.router, prefix="/api/v1/documents")
        test_app.dependency_overrides[get_db] = override_get_db
        test_app.dependency_overrides[get_action_logger] = override_get_action_logger
        test_app.dependency_overrides[get_chromadb] = override_get_chromadb
        test_app.dependency_overrides[get_embedding_service] = (
            override_get_embedding_service
        )

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as c:
            yield c


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_libraries_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/documents/libraries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []


@pytest.mark.asyncio
async def test_create_library(client: AsyncClient, mock_chromadb: Any) -> None:
    resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Test Library"}
    )
    assert resp.status_code == 201
    body = resp.json()
    lib = body["data"]
    assert lib["name"] == "Test Library"
    assert lib["doc_count"] == 0
    assert lib["chunk_count"] == 0
    assert lib["parse_quality"] is None
    # ChromaDB collection created
    mock_chromadb.create_collection.assert_awaited_once_with(lib["id"])


@pytest.mark.asyncio
async def test_list_libraries_returns_created(client: AsyncClient) -> None:
    await client.post("/api/v1/documents/libraries", json={"name": "Library A"})
    await client.post("/api/v1/documents/libraries", json={"name": "Library B"})
    resp = await client.get("/api/v1/documents/libraries")
    assert resp.status_code == 200
    names = [lib["name"] for lib in resp.json()["data"]]
    assert "Library A" in names
    assert "Library B" in names


@pytest.mark.asyncio
async def test_delete_library(client: AsyncClient, mock_chromadb: Any) -> None:
    create_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "To Delete"}
    )
    lib_id = create_resp.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/documents/libraries/{lib_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == lib_id

    # ChromaDB collection deleted
    mock_chromadb.delete_collection.assert_awaited_with(lib_id)

    # Verify gone
    list_resp = await client.get("/api/v1/documents/libraries")
    assert all(lib["id"] != lib_id for lib in list_resp.json()["data"])


@pytest.mark.asyncio
async def test_delete_library_not_found(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/documents/libraries/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Upload Test"}
    )
    lib_id = create_resp.json()["data"]["id"]

    content = b"Hello world document content"
    resp = await client.post(
        f"/api/v1/documents/libraries/{lib_id}/upload",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["document"]["filename"] == "test.txt"
    assert data["document"]["library_id"] == lib_id
    assert data["parse_tier"] == "basic"
    assert "file_hash" in data["document"]


@pytest.mark.asyncio
async def test_upload_document_library_not_found(client: AsyncClient) -> None:
    content = b"Hello world"
    resp = await client.post(
        "/api/v1/documents/libraries/bad-lib-id/upload",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_too_large(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Size Test"}
    )
    lib_id = create_resp.json()["data"]["id"]

    # 51 MB file
    large_content = b"x" * (51 * 1024 * 1024)
    resp = await client.post(
        f"/api/v1/documents/libraries/{lib_id}/upload",
        files={"file": ("big.txt", io.BytesIO(large_content), "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "GUARDRAIL_EXCEEDED"


@pytest.mark.asyncio
async def test_remove_document(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Remove Test"}
    )
    lib_id = create_resp.json()["data"]["id"]

    upload_resp = await client.post(
        f"/api/v1/documents/libraries/{lib_id}/upload",
        files={"file": ("doc.txt", io.BytesIO(b"content"), "text/plain")},
    )
    doc_id = upload_resp.json()["data"]["document"]["id"]

    resp = await client.delete(f"/api/v1/documents/libraries/{lib_id}/docs/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == doc_id


@pytest.mark.asyncio
async def test_remove_document_not_found(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Remove Test 2"}
    )
    lib_id = create_resp.json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/documents/libraries/{lib_id}/docs/nonexistent-doc"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Attach / Detach
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_and_detach_library(client: AsyncClient) -> None:
    lib_resp = await client.post(
        "/api/v1/documents/libraries", json={"name": "Attach Test"}
    )
    lib_id = lib_resp.json()["data"]["id"]
    session_id = "sess-attach-test"

    attach_resp = await client.post(
        f"/api/v1/documents/libraries/{lib_id}/attach",
        json={"session_id": session_id},
    )
    assert attach_resp.status_code == 200
    assert attach_resp.json()["data"]["attached"] == lib_id

    detach_resp = await client.post(
        "/api/v1/documents/libraries/detach",
        json={"session_id": session_id},
    )
    assert detach_resp.status_code == 200
    assert detach_resp.json()["data"]["detached"] is True


@pytest.mark.asyncio
async def test_attach_library_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/documents/libraries/bad-lib/attach",
        json={"session_id": "sess-xyz"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detach_no_attachment(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/documents/libraries/detach",
        json={"session_id": "sess-no-attachment"},
    )
    assert resp.status_code == 404
