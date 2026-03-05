"""Document library CRUD service.

Manages library entries, document tracking, session attachments, and
library statistics in the SQLite database.  ChromaDB collection lifecycle
(create/delete) is handled externally by the router layer, which receives
a ChromaDBClient dependency and calls into this service for the SQLite side.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Document, DocumentLibrary, SessionLibraryAttachment
from app.models.schemas import (
    DocumentLibraryResponse,
    DocumentResponse,
    DocumentUploadResponse,
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


# Parse quality tier ordering: higher index = higher quality
_TIER_RANK = {"basic": 0, "standard": 1, "high": 2}


class LibraryService:
    """CRUD for document libraries, documents, and session attachments."""

    # ------------------------------------------------------------------
    # Library CRUD
    # ------------------------------------------------------------------

    async def list_all(self, db: AsyncSession) -> list[DocumentLibraryResponse]:
        """Return all libraries ordered by name."""
        result = await db.execute(
            select(DocumentLibrary).order_by(DocumentLibrary.name)
        )
        rows = result.scalars().all()
        return [self._lib_to_response(r) for r in rows]

    async def get(
        self, db: AsyncSession, library_id: str
    ) -> DocumentLibraryResponse | None:
        """Get a single library by ID.  Returns None if not found."""
        row = await db.get(DocumentLibrary, library_id)
        if row is None:
            return None
        return self._lib_to_response(row)

    async def create(self, db: AsyncSession, name: str) -> DocumentLibraryResponse:
        """Create a new empty library entry."""
        lib = DocumentLibrary(
            id=f"lib-{uuid.uuid4().hex[:12]}",
            name=name,
            created_at=_utcnow(),
            doc_count=0,
            chunk_count=0,
            parse_quality=None,
            indexed_at=None,
        )
        db.add(lib)
        await db.commit()
        await db.refresh(lib)
        return self._lib_to_response(lib)

    async def delete(self, db: AsyncSession, library_id: str) -> bool:
        """Delete a library and all its documents.

        Callers are responsible for also deleting the ChromaDB collection.
        Returns False if the library was not found.
        """
        row = await db.get(DocumentLibrary, library_id)
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # Document tracking
    # ------------------------------------------------------------------

    async def add_document(
        self,
        db: AsyncSession,
        library_id: str,
        filename: str,
        file_hash: str,
        parse_tier: str,
        chunk_count: int,
    ) -> DocumentResponse:
        """Record an ingested document and recompute library stats."""
        doc = Document(
            id=f"doc-{uuid.uuid4().hex[:12]}",
            library_id=library_id,
            filename=filename,
            file_hash=file_hash,
            parse_tier=parse_tier,
            chunk_count=chunk_count,
            uploaded_at=_utcnow(),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        await self.update_stats(db, library_id)
        return self._doc_to_response(doc)

    async def remove_document(
        self, db: AsyncSession, library_id: str, doc_id: str
    ) -> bool:
        """Remove a document from a library and recompute stats.

        Callers are responsible for deleting the vectors from ChromaDB.
        Returns False if not found.
        """
        row = await db.get(Document, doc_id)
        if row is None or row.library_id != library_id:
            return False
        await db.delete(row)
        await db.commit()
        await self.update_stats(db, library_id)
        return True

    async def get_document_by_hash(
        self, db: AsyncSession, library_id: str, file_hash: str
    ) -> DocumentResponse | None:
        """Return the existing document record for a given hash, or None."""
        result = await db.execute(
            select(Document).where(
                Document.library_id == library_id,
                Document.file_hash == file_hash,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._doc_to_response(row)

    async def list_documents(
        self, db: AsyncSession, library_id: str
    ) -> list[DocumentResponse]:
        """List all documents in a library ordered by upload time."""
        result = await db.execute(
            select(Document)
            .where(Document.library_id == library_id)
            .order_by(Document.uploaded_at)
        )
        rows = result.scalars().all()
        return [self._doc_to_response(r) for r in rows]

    # ------------------------------------------------------------------
    # Session attachment
    # ------------------------------------------------------------------

    async def attach_to_session(
        self, db: AsyncSession, session_id: str, library_id: str
    ) -> None:
        """Attach a library to a session (replaces any prior attachment)."""
        # Remove any existing attachment for this session
        existing = await db.get(SessionLibraryAttachment, session_id)
        if existing is not None:
            await db.delete(existing)
            await db.flush()

        attachment = SessionLibraryAttachment(
            session_id=session_id,
            library_id=library_id,
            attached_at=_utcnow(),
        )
        db.add(attachment)
        await db.commit()

    async def detach_from_session(self, db: AsyncSession, session_id: str) -> bool:
        """Remove the library attachment from a session.  Returns False if none."""
        existing = await db.get(SessionLibraryAttachment, session_id)
        if existing is None:
            return False
        await db.delete(existing)
        await db.commit()
        return True

    async def get_attached_library(
        self, db: AsyncSession, session_id: str
    ) -> DocumentLibraryResponse | None:
        """Return the library currently attached to a session, or None."""
        attachment = await db.get(SessionLibraryAttachment, session_id)
        if attachment is None:
            return None
        return await self.get(db, attachment.library_id)

    # ------------------------------------------------------------------
    # Stats recomputation
    # ------------------------------------------------------------------

    async def update_stats(self, db: AsyncSession, library_id: str) -> None:
        """Recompute doc_count, chunk_count, parse_quality, and indexed_at."""
        lib = await db.get(DocumentLibrary, library_id)
        if lib is None:
            return

        # Aggregate counts
        count_result = await db.execute(
            select(
                func.count(Document.id),
                func.sum(Document.chunk_count),
            ).where(Document.library_id == library_id)
        )
        doc_count, chunk_sum = count_result.one()
        lib.doc_count = doc_count or 0
        lib.chunk_count = int(chunk_sum or 0)

        # Derive parse_quality as the lowest tier present (weakest link)
        tiers_result = await db.execute(
            select(Document.parse_tier).where(Document.library_id == library_id)
        )
        tiers = [row[0] for row in tiers_result.all()]
        if tiers:
            lib.parse_quality = min(tiers, key=lambda t: _TIER_RANK.get(t, 0))
            lib.indexed_at = _utcnow()
        else:
            lib.parse_quality = None
            lib.indexed_at = None

        await db.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lib_to_response(row: DocumentLibrary) -> DocumentLibraryResponse:
        return DocumentLibraryResponse(
            id=row.id,
            name=row.name,
            created_at=row.created_at,
            doc_count=row.doc_count,
            chunk_count=row.chunk_count,
            parse_quality=row.parse_quality,
            indexed_at=row.indexed_at,
        )

    @staticmethod
    def _doc_to_response(row: Document) -> DocumentResponse:
        return DocumentResponse(
            id=row.id,
            library_id=row.library_id,
            filename=row.filename,
            file_hash=row.file_hash,
            parse_tier=row.parse_tier,
            chunk_count=row.chunk_count,
            uploaded_at=row.uploaded_at,
        )

    @staticmethod
    def _doc_to_upload_response(row: Document) -> DocumentUploadResponse:
        return DocumentUploadResponse(
            document_id=row.id,
            filename=row.filename,
            parse_tier=row.parse_tier,
            chunk_count=row.chunk_count,
        )
