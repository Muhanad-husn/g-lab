"""Full document ingestion pipeline.

Orchestrates: SHA-256 hash → dedup check → tiered parsing
(Docling → Unstructured → Raw) → chunking → embedding →
ChromaDB storage → SQLite update.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.schemas import DocumentResponse, DocumentUploadResponse
from app.services.documents.chromadb_client import ChromaDBClient
from app.services.documents.chunking import ChunkingService
from app.services.documents.embeddings import EmbeddingService
from app.services.documents.library_service import LibraryService
from app.services.documents.parsers.base import ParseResult
from app.services.documents.parsers.raw_parser import RawParser
from app.services.documents.parsers.unstructured_parser import UnstructuredParser

logger: Any = get_logger(__name__)


class IngestionError(Exception):
    """Raised when document ingestion fails at all parser tiers."""


class IngestionService:
    """Full tiered document ingestion pipeline.

    Constructor takes the external service dependencies; the :meth:`ingest`
    method takes per-call data.

    Usage::

        svc = IngestionService(chromadb_client=chroma, embedding_service=emb)
        result = await svc.ingest(
            db=db,
            library_id="lib-abc",
            file_path=Path("/tmp/upload.pdf"),
            filename="report.pdf",
            mime_type="application/pdf",
        )
        print(result.parse_tier, result.chunk_count)
    """

    def __init__(
        self,
        chromadb_client: ChromaDBClient,
        embedding_service: EmbeddingService,
        library_svc: LibraryService | None = None,
    ) -> None:
        self._chroma = chromadb_client
        self._embeddings = embedding_service
        self._library_svc = library_svc or LibraryService()
        self._chunker = ChunkingService()

    async def ingest(
        self,
        *,
        db: AsyncSession,
        library_id: str,
        file_path: Path,
        filename: str,
        mime_type: str,
    ) -> DocumentUploadResponse:
        """Run the full ingestion pipeline for one document.

        Steps:

        1. Compute SHA-256 hash of the file.
        2. Dedup: if the same hash already exists in the library, delete its
           ChromaDB chunks and SQLite record before re-ingesting.
        3. Try each parser in tier order: Docling → Unstructured → Raw.
        4. Chunk the parse result using :class:`ChunkingService`.
        5. Embed all chunk texts using :class:`EmbeddingService`.
        6. Record the document in SQLite via :class:`LibraryService`.
        7. Store chunks and embeddings in ChromaDB (if connected).
        8. Return a :class:`DocumentUploadResponse`.

        Args:
            db:         Async SQLAlchemy session.
            library_id: Target library ID.
            file_path:  Path to the uploaded file on disk.
            filename:   Original filename (for metadata).
            mime_type:  MIME type used to select sub-parsers.

        Returns:
            :class:`DocumentUploadResponse` with parse tier and chunk count.

        Raises:
            IngestionError: If all parser tiers fail.
        """
        # Step 1: Hash
        file_hash = self._hash_file(file_path)

        # Step 2: Dedup — remove existing document with the same hash
        existing = await self._library_svc.get_document_by_hash(
            db, library_id, file_hash
        )
        if existing is not None:
            await self._delete_chunks(library_id, existing)
            await self._library_svc.remove_document(db, library_id, existing.id)
            logger.info(
                "ingestion_dedup_removed",
                doc_id=existing.id,
                library_id=library_id,
            )

        # Step 3: Parse (tiered fallback)
        parse_result = self._parse(file_path, mime_type)

        # Step 4: Chunk
        chunks = self._chunker.chunk(parse_result)

        # Step 5: Embed
        texts = [c.text for c in chunks]
        embeddings = await self._embeddings.embed(texts) if texts else []

        # Step 6: Record in SQLite
        doc = await self._library_svc.add_document(
            db,
            library_id=library_id,
            filename=filename,
            file_hash=file_hash,
            parse_tier=parse_result.parse_tier,
            chunk_count=len(chunks),
        )

        # Step 7: Store in ChromaDB
        if chunks and self._chroma.is_connected():
            ids = [f"{doc.id}-{chunk.index}" for chunk in chunks]
            metadatas = [
                {
                    "doc_id": doc.id,
                    "library_id": library_id,
                    "chunk_index": chunk.index,
                    "parse_tier": chunk.parse_tier,
                    # ChromaDB metadata does not support None values
                    "page_number": chunk.page_number
                    if chunk.page_number is not None
                    else -1,
                    "section_heading": chunk.section_heading or "",
                    "filename": filename,
                }
                for chunk in chunks
            ]
            await self._chroma.add_documents(
                collection=library_id,
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts,
            )
            logger.info(
                "ingestion_chunks_stored",
                library_id=library_id,
                doc_id=doc.id,
                chunk_count=len(chunks),
            )

        logger.info(
            "ingestion_complete",
            library_id=library_id,
            doc_id=doc.id,
            parse_tier=parse_result.parse_tier,
            chunk_count=len(chunks),
        )

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            parse_tier=parse_result.parse_tier,
            chunk_count=len(chunks),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        """Compute the SHA-256 hex digest of the file at *file_path*."""
        h = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    async def _delete_chunks(self, library_id: str, doc: DocumentResponse) -> None:
        """Remove all ChromaDB chunks for an existing document record."""
        if not self._chroma.is_connected() or doc.chunk_count == 0:
            return
        ids = [f"{doc.id}-{i}" for i in range(doc.chunk_count)]
        await self._chroma.delete_documents(library_id, ids)
        logger.info(
            "ingestion_dedup_chunks_deleted",
            doc_id=doc.id,
            count=len(ids),
        )

    def _parse(self, file_path: Path, mime_type: str) -> ParseResult:
        """Try parsers in tier order: Docling → Unstructured → Raw.

        Each tier's failure is logged as a warning.  If all three tiers
        fail, raises :class:`IngestionError`.
        """
        # Tier 1: Docling (highest quality)
        try:
            from app.services.documents.parsers.docling_parser import DoclingParser

            return DoclingParser().parse(file_path, mime_type)
        except Exception as exc:
            logger.warning("ingestion_tier1_failed", error=str(exc))

        # Tier 2: Unstructured (standard quality)
        try:
            return UnstructuredParser().parse(file_path, mime_type)
        except Exception as exc:
            logger.warning("ingestion_tier2_failed", error=str(exc))

        # Tier 3: Raw fallback (basic quality)
        try:
            return RawParser().parse(file_path, mime_type)
        except Exception as exc:
            raise IngestionError(
                f"All parser tiers failed for {file_path}: {exc}"
            ) from exc
