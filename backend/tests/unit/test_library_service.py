"""Unit tests for LibraryService using in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import Base
from app.services.documents.library_service import LibraryService


@pytest.fixture()
async def db() -> AsyncSession:  # type: ignore[return]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def svc() -> LibraryService:
    return LibraryService()


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty(db: AsyncSession, svc: LibraryService) -> None:
    result = await svc.list_all(db)
    assert result == []


@pytest.mark.asyncio
async def test_create_library(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "Test Library")
    assert lib.name == "Test Library"
    assert lib.id.startswith("lib-")
    assert lib.doc_count == 0
    assert lib.chunk_count == 0
    assert lib.parse_quality is None
    assert lib.indexed_at is None


@pytest.mark.asyncio
async def test_get_existing(db: AsyncSession, svc: LibraryService) -> None:
    created = await svc.create(db, "Alpha")
    fetched = await svc.get(db, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Alpha"


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(
    db: AsyncSession, svc: LibraryService
) -> None:
    result = await svc.get(db, "no-such-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_sorted_by_name(db: AsyncSession, svc: LibraryService) -> None:
    await svc.create(db, "Zeta")
    await svc.create(db, "Alpha")
    await svc.create(db, "Mu")
    libs = await svc.list_all(db)
    names = [l.name for l in libs]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_delete_existing(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "ToDelete")
    deleted = await svc.delete(db, lib.id)
    assert deleted is True
    assert await svc.get(db, lib.id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(
    db: AsyncSession, svc: LibraryService
) -> None:
    result = await svc.delete(db, "no-such-id")
    assert result is False


# ---------------------------------------------------------------------------
# Document tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_document(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "DocLib")
    doc = await svc.add_document(
        db,
        library_id=lib.id,
        filename="report.pdf",
        file_hash="abc123",
        parse_tier="high",
        chunk_count=10,
    )
    assert doc.id.startswith("doc-")
    assert doc.filename == "report.pdf"
    assert doc.parse_tier == "high"
    assert doc.chunk_count == 10


@pytest.mark.asyncio
async def test_add_document_updates_stats(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib = await svc.create(db, "StatsLib")
    await svc.add_document(db, lib.id, "a.pdf", "hash1", "high", 5)
    await svc.add_document(db, lib.id, "b.pdf", "hash2", "standard", 3)
    updated = await svc.get(db, lib.id)
    assert updated is not None
    assert updated.doc_count == 2
    assert updated.chunk_count == 8
    # parse_quality = weakest tier present
    assert updated.parse_quality == "standard"
    assert updated.indexed_at is not None


@pytest.mark.asyncio
async def test_stats_quality_weakest_link(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib = await svc.create(db, "MixedTiers")
    await svc.add_document(db, lib.id, "a.pdf", "h1", "high", 4)
    await svc.add_document(db, lib.id, "b.pdf", "h2", "basic", 2)
    await svc.add_document(db, lib.id, "c.pdf", "h3", "standard", 6)
    updated = await svc.get(db, lib.id)
    assert updated is not None
    assert updated.parse_quality == "basic"


@pytest.mark.asyncio
async def test_remove_document(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "RemoveLib")
    doc = await svc.add_document(db, lib.id, "x.pdf", "hashx", "high", 7)
    removed = await svc.remove_document(db, lib.id, doc.id)
    assert removed is True
    docs = await svc.list_documents(db, lib.id)
    assert docs == []


@pytest.mark.asyncio
async def test_remove_document_updates_stats(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib = await svc.create(db, "RemoveStats")
    doc = await svc.add_document(db, lib.id, "x.pdf", "hashx", "high", 7)
    await svc.remove_document(db, lib.id, doc.id)
    updated = await svc.get(db, lib.id)
    assert updated is not None
    assert updated.doc_count == 0
    assert updated.chunk_count == 0
    assert updated.parse_quality is None


@pytest.mark.asyncio
async def test_remove_document_wrong_library(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib1 = await svc.create(db, "Lib1")
    lib2 = await svc.create(db, "Lib2")
    doc = await svc.add_document(db, lib1.id, "x.pdf", "hashx", "high", 2)
    result = await svc.remove_document(db, lib2.id, doc.id)
    assert result is False


@pytest.mark.asyncio
async def test_get_document_by_hash(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "HashLib")
    await svc.add_document(db, lib.id, "doc.pdf", "sha256abc", "high", 5)
    found = await svc.get_document_by_hash(db, lib.id, "sha256abc")
    assert found is not None
    assert found.filename == "doc.pdf"


@pytest.mark.asyncio
async def test_get_document_by_hash_missing(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib = await svc.create(db, "HashLib2")
    result = await svc.get_document_by_hash(db, lib.id, "nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# Session attachment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_and_get(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "AttachLib")
    await svc.attach_to_session(db, "session-1", lib.id)
    attached = await svc.get_attached_library(db, "session-1")
    assert attached is not None
    assert attached.id == lib.id


@pytest.mark.asyncio
async def test_attach_replaces_existing(
    db: AsyncSession, svc: LibraryService
) -> None:
    lib1 = await svc.create(db, "Lib1")
    lib2 = await svc.create(db, "Lib2")
    await svc.attach_to_session(db, "session-x", lib1.id)
    await svc.attach_to_session(db, "session-x", lib2.id)
    attached = await svc.get_attached_library(db, "session-x")
    assert attached is not None
    assert attached.id == lib2.id


@pytest.mark.asyncio
async def test_detach_from_session(db: AsyncSession, svc: LibraryService) -> None:
    lib = await svc.create(db, "DetachLib")
    await svc.attach_to_session(db, "session-2", lib.id)
    detached = await svc.detach_from_session(db, "session-2")
    assert detached is True
    assert await svc.get_attached_library(db, "session-2") is None


@pytest.mark.asyncio
async def test_detach_no_attachment_returns_false(
    db: AsyncSession, svc: LibraryService
) -> None:
    result = await svc.detach_from_session(db, "session-no-attachment")
    assert result is False


@pytest.mark.asyncio
async def test_get_attached_library_none(
    db: AsyncSession, svc: LibraryService
) -> None:
    result = await svc.get_attached_library(db, "unattached-session")
    assert result is None


# ---------------------------------------------------------------------------
# Delete library removes from DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_with_documents_removes_library(
    db: AsyncSession, svc: LibraryService
) -> None:
    """Deleting a library removes it from the DB (FK cascade is DB-level)."""
    lib = await svc.create(db, "CascadeLib")
    await svc.add_document(db, lib.id, "a.pdf", "h1", "high", 3)
    await svc.add_document(db, lib.id, "b.pdf", "h2", "standard", 2)
    deleted = await svc.delete(db, lib.id)
    assert deleted is True
    # Library is gone
    assert await svc.get(db, lib.id) is None
