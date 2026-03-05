"""Documents and document library endpoints.

All endpoints are prefixed with /api/v1/documents (set in main.py).
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.dependencies import (
    get_action_logger,
    get_chromadb,
    get_db,
    get_embedding_service,
)
from app.models.enums import ActionType
from app.models.schemas import (
    DocumentLibraryCreate,
    DocumentUploadResponse,
    LibraryAttachRequest,
)
from app.services.action_log import ActionLogger
from app.services.documents.chromadb_client import ChromaDBClient
from app.services.documents.embeddings import EmbeddingService
from app.services.documents.library_service import LibraryService
from app.services.guardrails import GuardrailService
from app.utils.response import envelope, error_response

router = APIRouter()
_svc = LibraryService()

# Placeholder session_id for library-level actions (not tied to a session)
_SYSTEM_SESSION = "system"
_guardrails = GuardrailService()


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


@router.get("/libraries")
async def list_libraries(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all document libraries."""
    libraries = await _svc.list_all(db)
    return envelope([lib.model_dump() for lib in libraries])


@router.post("/libraries", status_code=201)
async def create_library(
    body: DocumentLibraryCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    chromadb_client: ChromaDBClient | None = Depends(get_chromadb),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Create a new document library."""
    library = await _svc.create(db, body.name)

    # Create matching ChromaDB collection if available
    if chromadb_client is not None and chromadb_client.is_connected():
        await chromadb_client.create_collection(library.id)

    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.LIBRARY_CREATE,
        actor="user",
        payload={"library_id": library.id, "name": library.name},
    )
    return envelope(library.model_dump())


@router.delete("/libraries/{library_id}")
async def delete_library(
    library_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    chromadb_client: ChromaDBClient | None = Depends(get_chromadb),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Delete a library and all its documents from SQLite and ChromaDB."""
    deleted = await _svc.delete(db, library_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Library not found")

    # Delete ChromaDB collection if available
    if chromadb_client is not None and chromadb_client.is_connected():
        await chromadb_client.delete_collection(library_id)

    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.LIBRARY_DELETE,
        actor="user",
        payload={"library_id": library_id},
    )
    return envelope({"deleted": library_id})


# ---------------------------------------------------------------------------
# Document upload / remove
# ---------------------------------------------------------------------------


@router.post("/libraries/{library_id}/upload", status_code=201, response_model=None)
async def upload_documents(
    library_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(default=[]),
    session_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    chromadb_client: ChromaDBClient | None = Depends(get_chromadb),
    embedding_service: EmbeddingService | None = Depends(get_embedding_service),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any] | Response:
    """Upload one or more documents to a library.

    Guardrails: 50 MB max file size, 100 documents per library.
    """
    if not files:
        raise HTTPException(status_code=422, detail="No files provided")

    library = await _svc.get(db, library_id)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")

    results: list[dict[str, Any]] = []
    doc_count_offset = library.doc_count

    for file in files:
        content = await file.read()
        file_size = len(content)

        # Guardrail: file size + doc count (use running count)
        guard = _guardrails.check_doc_upload(file_size, doc_count_offset)
        if not guard.allowed:
            return JSONResponse(
                status_code=400 if "file_size_mb" in (guard.detail or {}) else 409,
                content=error_response(
                    code="GUARDRAIL_EXCEEDED",
                    message="Upload rejected by guardrail",
                    detail=guard.detail,
                ),
            )

        file_hash = hashlib.sha256(content).hexdigest()
        filename = file.filename or "unknown"

        doc = await _svc.add_document(
            db,
            library_id=library_id,
            filename=filename,
            file_hash=file_hash,
            parse_tier="basic",
            chunk_count=0,
        )
        doc_count_offset += 1

        background_tasks.add_task(
            action_logger.log,
            session_id=session_id or _SYSTEM_SESSION,
            action_type=ActionType.DOC_UPLOAD,
            actor="user",
            payload={
                "library_id": library_id,
                "doc_id": doc.id,
                "filename": filename,
                "file_size_bytes": file_size,
            },
        )

        results.append(
            DocumentUploadResponse(
                document_id=doc.id,
                filename=doc.filename,
                parse_tier=doc.parse_tier,
                chunk_count=doc.chunk_count,
            ).model_dump()
        )

    return envelope(results)


@router.delete("/libraries/{library_id}/docs/{doc_id}")
async def remove_document(
    library_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Remove a document from a library."""
    deleted = await _svc.remove_document(db, library_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    background_tasks.add_task(
        action_logger.log,
        session_id=_SYSTEM_SESSION,
        action_type=ActionType.DOC_DELETE,
        actor="user",
        payload={"library_id": library_id, "doc_id": doc_id},
    )
    return envelope({"deleted": doc_id})


# ---------------------------------------------------------------------------
# Session attachment
# ---------------------------------------------------------------------------


@router.get("/libraries/attached/{session_id}")
async def get_attached_library(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the library currently attached to a session, if any."""
    library = await _svc.get_attached_library(db, session_id)
    return envelope({"library_id": library.id if library else None})


@router.post("/libraries/{library_id}/attach")
async def attach_library(
    library_id: str,
    body: LibraryAttachRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Attach a library to a session (replaces any prior attachment)."""
    library = await _svc.get(db, library_id)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")

    await _svc.attach_to_session(db, body.session_id, library_id)

    background_tasks.add_task(
        action_logger.log,
        session_id=body.session_id,
        action_type=ActionType.LIBRARY_ATTACH,
        actor="user",
        payload={"library_id": library_id, "session_id": body.session_id},
    )
    return envelope({"attached": library_id, "session_id": body.session_id})


@router.post("/libraries/detach")
async def detach_library(
    body: LibraryAttachRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    action_logger: ActionLogger = Depends(get_action_logger),
) -> dict[str, Any]:
    """Detach the library from a session."""
    detached = await _svc.detach_from_session(db, body.session_id)
    if not detached:
        raise HTTPException(
            status_code=404, detail="No library attached to this session"
        )

    background_tasks.add_task(
        action_logger.log,
        session_id=body.session_id,
        action_type=ActionType.LIBRARY_DETACH,
        actor="user",
        payload={"session_id": body.session_id},
    )
    return envelope({"detached": True, "session_id": body.session_id})
