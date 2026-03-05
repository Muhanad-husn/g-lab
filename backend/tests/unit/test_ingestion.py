"""Unit tests for IngestionService (tiered pipeline), fully mocked."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub third-party libs used transitively by the modules under test
# so this file can be collected without those packages installed.
# ---------------------------------------------------------------------------
for _mod in (
    "unstructured",
    "unstructured.partition",
    "unstructured.partition.pdf",
    "unstructured.partition.docx",
    "PyPDF2",
    "docx",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "docling" not in sys.modules:
    sys.modules["docling"] = MagicMock()
if "docling.document_converter" not in sys.modules:
    sys.modules["docling.document_converter"] = MagicMock()

from app.models.schemas import DocumentResponse, DocumentUploadResponse  # noqa: E402
from app.services.documents.ingestion import IngestionError, IngestionService  # noqa: E402
from app.services.documents.parsers.base import ParseResult, Section  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PDF_MIME = "application/pdf"


def _doc_response(**kwargs: object) -> DocumentResponse:
    defaults: dict[str, object] = {
        "id": "doc-abc123",
        "library_id": "lib-xyz",
        "filename": "test.pdf",
        "file_hash": "a" * 64,
        "parse_tier": "high",
        "chunk_count": 2,
        "uploaded_at": "2024-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return DocumentResponse(**defaults)  # type: ignore[arg-type]


def _parse_result(tier: str = "high") -> ParseResult:
    return ParseResult(
        text="Intro text here. Body content follows with more words to chunk.",
        sections=[
            Section(
                content="Intro text here.",
                heading="Introduction",
                page_number=1,
            ),
            Section(
                content="Body content follows with more words to chunk.",
                heading="Body",
                page_number=2,
            ),
        ],
        parse_tier=tier,
    )


def _make_service(
    chroma: MagicMock | None = None,
    embeddings: MagicMock | None = None,
    library_svc: MagicMock | None = None,
) -> IngestionService:
    if chroma is None:
        chroma = MagicMock()
        chroma.is_connected.return_value = True
        chroma.add_documents = AsyncMock()
        chroma.delete_documents = AsyncMock()
    if embeddings is None:
        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])
    svc = IngestionService(
        chromadb_client=chroma,
        embedding_service=embeddings,
        library_svc=library_svc,
    )
    return svc


# ---------------------------------------------------------------------------
# Tier cascade tests
# ---------------------------------------------------------------------------


class TestIngestionTierCascade:
    @pytest.mark.asyncio
    async def test_tier1_success_returns_high_parse_tier(self) -> None:
        """When Docling succeeds, parse_tier="high" is used."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        doc = _doc_response(parse_tier="high", chunk_count=2)
        lib_svc.add_document = AsyncMock(return_value=doc)

        svc = _make_service(library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch("app.services.documents.parsers.docling_parser.DoclingParser.parse", return_value=_parse_result("high")),
        ):
            result = await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        assert result.parse_tier == "high"
        assert isinstance(result, DocumentUploadResponse)

    @pytest.mark.asyncio
    async def test_tier1_fails_tier2_succeeds_returns_standard(self) -> None:
        """Docling failure → Unstructured used → parse_tier="standard"."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        doc = _doc_response(parse_tier="standard", chunk_count=2)
        lib_svc.add_document = AsyncMock(return_value=doc)

        svc = _make_service(library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                side_effect=Exception("docling unavailable"),
            ),
            patch(
                "app.services.documents.parsers.unstructured_parser.UnstructuredParser.parse",
                return_value=_parse_result("standard"),
            ),
        ):
            result = await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        assert result.parse_tier == "standard"

    @pytest.mark.asyncio
    async def test_tier1_tier2_fail_tier3_succeeds_returns_basic(self) -> None:
        """Docling + Unstructured both fail → Raw used → parse_tier="basic"."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        doc = _doc_response(parse_tier="basic", chunk_count=1)
        lib_svc.add_document = AsyncMock(return_value=doc)

        svc = _make_service(library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                side_effect=Exception("tier1 fail"),
            ),
            patch(
                "app.services.documents.parsers.unstructured_parser.UnstructuredParser.parse",
                side_effect=Exception("tier2 fail"),
            ),
            patch(
                "app.services.documents.parsers.raw_parser.RawParser.parse",
                return_value=_parse_result("basic"),
            ),
        ):
            result = await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        assert result.parse_tier == "basic"

    @pytest.mark.asyncio
    async def test_all_tiers_fail_raises_ingestion_error(self) -> None:
        """All three tiers failing raises IngestionError."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)

        svc = _make_service(library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                side_effect=Exception("tier1 fail"),
            ),
            patch(
                "app.services.documents.parsers.unstructured_parser.UnstructuredParser.parse",
                side_effect=Exception("tier2 fail"),
            ),
            patch(
                "app.services.documents.parsers.raw_parser.RawParser.parse",
                side_effect=Exception("tier3 fail"),
            ),
        ):
            with pytest.raises(IngestionError, match="All parser tiers failed"):
                await svc.ingest(
                    db=MagicMock(),
                    library_id="lib-xyz",
                    file_path=Path("report.pdf"),
                    filename="report.pdf",
                    mime_type=_PDF_MIME,
                )


# ---------------------------------------------------------------------------
# Dedup tests
# ---------------------------------------------------------------------------


class TestIngestionDedup:
    @pytest.mark.asyncio
    async def test_dedup_removes_old_document_before_reingest(self) -> None:
        """Same hash → old chunks deleted and old document removed."""
        old_doc = _doc_response(id="doc-old", chunk_count=3)
        new_doc = _doc_response(id="doc-new", chunk_count=2)

        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=old_doc)
        lib_svc.remove_document = AsyncMock(return_value=True)
        lib_svc.add_document = AsyncMock(return_value=new_doc)

        chroma = MagicMock()
        chroma.is_connected.return_value = True
        chroma.delete_documents = AsyncMock()
        chroma.add_documents = AsyncMock()

        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])

        svc = _make_service(chroma=chroma, embeddings=embeddings, library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=_parse_result("high"),
            ),
        ):
            await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        # Old chunks deleted from ChromaDB
        chroma.delete_documents.assert_awaited_once()
        args = chroma.delete_documents.call_args
        ids_deleted = args[0][1]
        assert len(ids_deleted) == 3  # old_doc.chunk_count
        assert all(id_.startswith("doc-old-") for id_ in ids_deleted)

        # Old document removed from SQLite
        lib_svc.remove_document.assert_awaited_once()
        rm_call_args = lib_svc.remove_document.call_args
        assert rm_call_args[0][1] == "lib-xyz"
        assert rm_call_args[0][2] == "doc-old"

    @pytest.mark.asyncio
    async def test_no_dedup_when_hash_not_found(self) -> None:
        """No existing doc → remove_document never called."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        lib_svc.remove_document = AsyncMock()
        lib_svc.add_document = AsyncMock(return_value=_doc_response())

        svc = _make_service(library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=_parse_result(),
            ),
        ):
            await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        lib_svc.remove_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedup_zero_chunks_skips_chromadb_delete(self) -> None:
        """Existing doc with chunk_count=0 → no ChromaDB delete call."""
        old_doc = _doc_response(id="doc-old", chunk_count=0)
        new_doc = _doc_response(id="doc-new", chunk_count=1)

        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=old_doc)
        lib_svc.remove_document = AsyncMock(return_value=True)
        lib_svc.add_document = AsyncMock(return_value=new_doc)

        chroma = MagicMock()
        chroma.is_connected.return_value = True
        chroma.delete_documents = AsyncMock()
        chroma.add_documents = AsyncMock()

        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[[0.1] * 384])

        svc = _make_service(chroma=chroma, embeddings=embeddings, library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=_parse_result(),
            ),
        ):
            await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        chroma.delete_documents.assert_not_awaited()


# ---------------------------------------------------------------------------
# ChromaDB storage tests
# ---------------------------------------------------------------------------


class TestIngestionStorage:
    @pytest.mark.asyncio
    async def test_chunks_stored_in_chromadb_with_correct_ids(self) -> None:
        """Chunk IDs follow {doc_id}-{index} pattern."""
        doc = _doc_response(id="doc-abc", chunk_count=2)
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        lib_svc.add_document = AsyncMock(return_value=doc)

        chroma = MagicMock()
        chroma.is_connected.return_value = True
        chroma.add_documents = AsyncMock()

        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])

        svc = _make_service(chroma=chroma, embeddings=embeddings, library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=_parse_result("high"),
            ),
        ):
            await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        chroma.add_documents.assert_awaited_once()
        call_kwargs = chroma.add_documents.call_args
        ids = call_kwargs[1]["ids"]
        assert ids[0] == "doc-abc-0"
        assert ids[1] == "doc-abc-1"

    @pytest.mark.asyncio
    async def test_chromadb_not_connected_skips_storage(self) -> None:
        """Disconnected ChromaDB → add_documents not called."""
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        doc = _doc_response(chunk_count=2)
        lib_svc.add_document = AsyncMock(return_value=doc)

        chroma = MagicMock()
        chroma.is_connected.return_value = False  # disconnected
        chroma.add_documents = AsyncMock()

        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])

        svc = _make_service(chroma=chroma, embeddings=embeddings, library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=_parse_result(),
            ),
        ):
            result = await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("report.pdf"),
                filename="report.pdf",
                mime_type=_PDF_MIME,
            )

        chroma.add_documents.assert_not_awaited()
        # Result still returned from SQLite record
        assert result.parse_tier == "high"

    @pytest.mark.asyncio
    async def test_empty_document_no_chromadb_call(self) -> None:
        """Document with no chunks → embed and add_documents not called."""
        empty_result = ParseResult(text="", sections=None, parse_tier="basic")
        lib_svc = MagicMock()
        lib_svc.get_document_by_hash = AsyncMock(return_value=None)
        doc = _doc_response(chunk_count=0)
        lib_svc.add_document = AsyncMock(return_value=doc)

        chroma = MagicMock()
        chroma.is_connected.return_value = True
        chroma.add_documents = AsyncMock()

        embeddings = MagicMock()
        embeddings.embed = AsyncMock(return_value=[])

        svc = _make_service(chroma=chroma, embeddings=embeddings, library_svc=lib_svc)

        with (
            patch("app.services.documents.ingestion.IngestionService._hash_file", return_value="h" * 64),
            patch(
                "app.services.documents.parsers.docling_parser.DoclingParser.parse",
                return_value=empty_result,
            ),
        ):
            result = await svc.ingest(
                db=MagicMock(),
                library_id="lib-xyz",
                file_path=Path("empty.pdf"),
                filename="empty.pdf",
                mime_type=_PDF_MIME,
            )

        chroma.add_documents.assert_not_awaited()
        assert result.chunk_count == 0


# ---------------------------------------------------------------------------
# Hash computation test
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_hash_file_returns_sha256_hex(self, tmp_path: Path) -> None:
        import hashlib

        content = b"Hello, World! This is test content."
        f = tmp_path / "test.bin"
        f.write_bytes(content)

        result = IngestionService._hash_file(f)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected
        assert len(result) == 64

    def test_hash_file_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert IngestionService._hash_file(f1) != IngestionService._hash_file(f2)
