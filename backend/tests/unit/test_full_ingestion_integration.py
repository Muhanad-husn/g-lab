"""Full ingestion pipeline integration test — all external services mocked.

Covers the complete Phase 3 flow end-to-end with no real IO:
  upload → parse → chunk → embed → store in ChromaDB
  → retrieve (vector search) → rerank → synthesise with doc context.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    ChunkMetadata,
    CopilotQueryRequest,
    DocumentChunk,
    DocumentResponse,
    DocumentUploadResponse,
    PresetConfig,
    RouterIntent,
)
from app.services.copilot.pipeline import CopilotPipeline
from app.services.copilot.sse import SSEEvent
from app.services.documents.ingestion import IngestionService
from app.services.documents.parsers.base import ParseResult
from app.services.documents.retrieval import DocumentRetrievalService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc_response(doc_id: str = "doc-abc") -> DocumentResponse:
    return DocumentResponse(
        id=doc_id,
        library_id="lib-1",
        filename="test.pdf",
        file_hash="abc123",
        parse_tier="basic",
        chunk_count=3,
        uploaded_at="2026-01-01T00:00:00+00:00",
    )


def _make_chunk(chunk_id: str, text: str = "relevant text") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            document_id="doc-abc",
            library_id="lib-1",
            page_number=1,
            section_heading=None,
            chunk_index=0,
            parse_tier="basic",
        ),
        similarity_score=0.8,
    )


def _chroma_query_result() -> dict[str, Any]:
    return {
        "ids": [["c1", "c2", "c3"]],
        "documents": [["text1", "text2", "text3"]],
        "metadatas": [
            [
                {
                    "document_id": "doc-1",
                    "library_id": "lib-1",
                    "chunk_index": 0,
                    "parse_tier": "basic",
                    "page_number": 1,
                    "section_heading": "",
                    "filename": "test.pdf",
                },
                {
                    "document_id": "doc-1",
                    "library_id": "lib-1",
                    "chunk_index": 1,
                    "parse_tier": "basic",
                    "page_number": 1,
                    "section_heading": "",
                    "filename": "test.pdf",
                },
                {
                    "document_id": "doc-1",
                    "library_id": "lib-1",
                    "chunk_index": 2,
                    "parse_tier": "basic",
                    "page_number": 2,
                    "section_heading": "",
                    "filename": "test.pdf",
                },
            ]
        ],
        "distances": [[0.1, 0.2, 0.3]],
    }


def _synth_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Corp Y owns Company X."}),
        SSEEvent(event="evidence", data={"sources": []}),
        SSEEvent(event="confidence", data={"score": 0.85, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


def _async_gen(events: list[SSEEvent]) -> AsyncGenerator[SSEEvent, None]:
    async def _gen() -> AsyncGenerator[SSEEvent, None]:
        for e in events:
            yield e

    return _gen()


# ---------------------------------------------------------------------------
# Ingestion: upload → parse → chunk → embed → store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_success_stores_in_chromadb() -> None:
    """Full ingest: parse OK → chunks embedded → stored in ChromaDB."""
    mock_chroma = MagicMock()
    mock_chroma.is_connected.return_value = True
    mock_chroma.add_documents = AsyncMock()
    mock_chroma.delete_documents = AsyncMock()
    mock_embeddings = AsyncMock()
    mock_embeddings.embed.return_value = [[0.1] * 384, [0.2] * 384, [0.3] * 384]
    mock_db = AsyncMock()
    doc_response = _make_doc_response()

    with (
        patch(
            "app.services.documents.ingestion.IngestionService._hash_file",
            return_value="deadbeef",
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.get_document_by_hash",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.add_document",
            new=AsyncMock(return_value=doc_response),
        ),
        patch(
            "app.services.documents.ingestion.IngestionService._parse",
            return_value=ParseResult(
                text="chunk one. chunk two. chunk three.",
                sections=None,
                parse_tier="basic",
            ),
        ),
    ):
        svc = IngestionService(
            chromadb_client=mock_chroma,
            embedding_service=mock_embeddings,
        )
        result = await svc.ingest(
            db=mock_db,
            library_id="lib-1",
            file_path=Path("/tmp/test.pdf"),
            filename="test.pdf",
            mime_type="application/pdf",
        )

    assert isinstance(result, DocumentUploadResponse)
    assert result.parse_tier == "basic"
    mock_embeddings.embed.assert_called_once()
    mock_chroma.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_dedup_removes_existing_before_reingest() -> None:
    """Same file hash → old chunks deleted before re-ingesting."""
    mock_chroma = MagicMock()
    mock_chroma.is_connected.return_value = True
    mock_chroma.add_documents = AsyncMock()
    mock_chroma.delete_documents = AsyncMock()
    mock_embeddings = AsyncMock()
    mock_embeddings.embed.return_value = [[0.1] * 384]
    existing_doc = _make_doc_response("old-doc")
    new_doc = _make_doc_response("new-doc")
    mock_db = AsyncMock()

    with (
        patch(
            "app.services.documents.ingestion.IngestionService._hash_file",
            return_value="same-hash",
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.get_document_by_hash",
            new=AsyncMock(return_value=existing_doc),
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.remove_document",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.add_document",
            new=AsyncMock(return_value=new_doc),
        ),
        patch(
            "app.services.documents.ingestion.IngestionService._parse",
            return_value=ParseResult(
                text="content", sections=None, parse_tier="basic"
            ),
        ),
    ):
        svc = IngestionService(
            chromadb_client=mock_chroma,
            embedding_service=mock_embeddings,
        )
        result = await svc.ingest(
            db=mock_db,
            library_id="lib-1",
            file_path=Path("/tmp/test.pdf"),
            filename="test.pdf",
            mime_type="application/pdf",
        )

    assert result.document.id == "new-doc"
    mock_chroma.delete_documents.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_chromadb_disconnected_skips_vector_store() -> None:
    """When ChromaDB is disconnected, SQLite records are still created."""
    mock_chroma = MagicMock()
    mock_chroma.is_connected.return_value = False
    mock_chroma.add_documents = AsyncMock()
    mock_chroma.delete_documents = AsyncMock()
    mock_embeddings = AsyncMock()
    mock_embeddings.embed.return_value = [[0.1] * 384]
    mock_db = AsyncMock()
    doc_response = _make_doc_response()

    with (
        patch(
            "app.services.documents.ingestion.IngestionService._hash_file",
            return_value="abc",
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.get_document_by_hash",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.documents.ingestion.LibraryService.add_document",
            new=AsyncMock(return_value=doc_response),
        ),
        patch(
            "app.services.documents.ingestion.IngestionService._parse",
            return_value=ParseResult(text="text", sections=None, parse_tier="basic"),
        ),
    ):
        svc = IngestionService(
            chromadb_client=mock_chroma,
            embedding_service=mock_embeddings,
        )
        result = await svc.ingest(
            db=mock_db,
            library_id="lib-1",
            file_path=Path("/tmp/test.pdf"),
            filename="test.pdf",
            mime_type="application/pdf",
        )

    assert isinstance(result, DocumentUploadResponse)
    mock_chroma.add_documents.assert_not_called()


# ---------------------------------------------------------------------------
# Retrieval: vector search maps ChromaDB results to DocumentChunk objects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_maps_chromadb_results() -> None:
    """embed query → ChromaDB → DocumentChunk list with correct metadata."""
    mock_chroma = MagicMock()
    mock_chroma.query = AsyncMock(return_value=_chroma_query_result())
    mock_embeddings = AsyncMock()
    mock_embeddings.embed_query.return_value = [0.5] * 384

    svc = DocumentRetrievalService(
        chroma_client=mock_chroma,
        embedding_service=mock_embeddings,
    )
    chunks = await svc.retrieve(
        query="Who owns company X?",
        library_id="lib-1",
        top_k=3,
    )

    assert len(chunks) == 3
    assert chunks[0].id == "c1"
    assert chunks[0].metadata.library_id == "lib-1"
    # Similarity = 1 - distance; first chunk distance 0.1 → similarity 0.9
    assert abs(chunks[0].similarity_score - 0.9) < 1e-6


@pytest.mark.asyncio
async def test_retrieval_empty_collection_returns_empty() -> None:
    """Empty ChromaDB result → empty list returned."""
    mock_chroma = MagicMock()
    mock_chroma.query = AsyncMock(
        return_value={"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    )
    mock_embeddings = AsyncMock()
    mock_embeddings.embed_query.return_value = [0.5] * 384

    svc = DocumentRetrievalService(
        chroma_client=mock_chroma,
        embedding_service=mock_embeddings,
    )
    chunks = await svc.retrieve(query="anything", library_id="lib-1", top_k=5)

    assert chunks == []


# ---------------------------------------------------------------------------
# End-to-end pipeline: graph + doc retrieval → synthesiser with doc context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_with_doc_context() -> None:
    """query → router (needs_docs=True) → parallel retrieval → synthesiser with chunks."""
    intent = RouterIntent(
        needs_graph=True,
        needs_docs=True,
        doc_query="company ownership",
    )
    doc_chunks = [_make_chunk("c1", "Corp Y owns Company X via subsidiary Z.")]
    events_list = _synth_events()

    mock_retrieval = AsyncMock()
    mock_reranker = AsyncMock()

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [], "")),
        ),
        patch(
            "app.services.copilot.pipeline.DocumentRetrievalRole.retrieve",
            new=AsyncMock(return_value=(doc_chunks, [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=_async_gen(events_list),
        ),
    ):
        pipeline = CopilotPipeline()
        collected: list[SSEEvent] = []
        async for event in pipeline.execute(
            request=CopilotQueryRequest(
                query="Who owns company X?", session_id="sess-1"
            ),
            neo4j_service=MagicMock(),
            openrouter_client=MagicMock(),
            preset_config=PresetConfig(),
            session_id="sess-1",
            semaphore=asyncio.Semaphore(1),
            retrieval_service=mock_retrieval,
            reranker_service=mock_reranker,
            library_id="lib-1",
        ):
            collected.append(event)

    event_types = [e.event for e in collected]
    assert "text_chunk" in event_types
    assert "done" in event_types
    assert any(
        e.event == "status" and e.data.get("stage") == "retrieving"
        for e in collected
    )


# ---------------------------------------------------------------------------
# Export: vector_manifest included in session archive
# ---------------------------------------------------------------------------


def test_pack_session_includes_vector_manifest() -> None:
    """pack_session writes vector_manifest.json when provided."""
    import zipfile
    import io
    from app.utils.export import pack_session

    vm = {
        "library_name": "Investigation Docs",
        "library_id": "lib-abc",
        "documents": [
            {"filename": "report.pdf", "parse_tier": "high"},
            {"filename": "filing.docx", "parse_tier": "basic"},
        ],
    }

    archive_bytes = pack_session(
        session_data={"id": "sess-1"},
        canvas_data={"nodes": [], "edges": []},
        findings_data=[],
        action_log_ndjson="",
        snapshots={},
        vector_manifest=vm,
    )

    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
        names = zf.namelist()
        assert "session-export/vector_manifest.json" in names
        import json
        loaded = json.loads(zf.read("session-export/vector_manifest.json"))
        assert loaded["library_name"] == "Investigation Docs"
        assert len(loaded["documents"]) == 2


def test_pack_session_omits_vector_manifest_when_none() -> None:
    """pack_session does not add vector_manifest.json when not provided."""
    import zipfile
    import io
    from app.utils.export import pack_session

    archive_bytes = pack_session(
        session_data={"id": "sess-1"},
        canvas_data={"nodes": [], "edges": []},
        findings_data=[],
        action_log_ndjson="",
        snapshots={},
    )

    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
        assert "session-export/vector_manifest.json" not in zf.namelist()
