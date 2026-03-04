# G-Lab Phase 3 — Implementation Plan

## Context

Phase 2 is complete (Stages 8–12, 14 runs). Phase 3 adds document grounding alongside graph retrieval. All Phase 1 and Phase 2 infrastructure is reused; no restructuring of prior code.

**Key references:** `docs/ARCHITECTURE.md` §8 (Document Ingestion Pipeline), §5.3 (Phase 3 endpoints), §6.1 (Phase 3 tables), §9 (guardrails), §2.4 (ChromaDB). `docs/PRODUCT.md` §9 (Document Library), §5 (pipeline diagram), §7 (guardrails). `backend/CLAUDE.md` and `frontend/CLAUDE.md` for coding conventions.

---

## Stage 13 — Document Infrastructure (3 runs)

### Run 13.1: ChromaDB Client, Config Extension, Embedding Setup
- `backend/app/services/documents/__init__.py` — package init
- `backend/app/services/documents/chromadb_client.py` — async ChromaDB HTTP client wrapper: `connect(host, port)`, `close()`, `is_connected()`, `create_collection(name)`, `delete_collection(name)`, `add_documents(collection, ids, embeddings, metadatas, documents)`, `query(collection, query_embedding, n_results, where_filter)`, `delete_documents(collection, ids)`, `get_collection_count(collection)`. Uses `chromadb.HttpClient`.
- `backend/app/services/documents/embeddings.py` — embedding service: `EmbeddingService.embed(texts: list[str]) -> list[list[float]]`, `embed_query(text) -> list[float]`. Uses `sentence-transformers` with configurable model (`all-MiniLM-L6-v2` default, 384 dims). Lazy model loading on first call.
- `backend/app/config.py` — extend Settings with `CHROMA_HOST: str = "chromadb"`, `CHROMA_PORT: int = 8000`, `EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"`
- `backend/tests/unit/test_chromadb_client.py` — mock httpx/chromadb: connect, add docs, query returns results, delete, collection CRUD
- `backend/tests/unit/test_embeddings.py` — mock sentence-transformers: embed returns correct dims, batch embed, embed_query

**Verify:** `pytest tests/unit/test_chromadb_client.py tests/unit/test_embeddings.py -x -v`

### Run 13.2: Migration, ORM Models, Schemas, Library Service
- `backend/alembic/versions/003_add_document_libraries.py` — creates `document_libraries` table (id TEXT PK, name TEXT NOT NULL, created_at TEXT NOT NULL, doc_count INTEGER DEFAULT 0, chunk_count INTEGER DEFAULT 0, parse_quality TEXT, indexed_at TEXT), `documents` table (id TEXT PK, library_id TEXT FK CASCADE, filename TEXT NOT NULL, file_hash TEXT NOT NULL, parse_tier TEXT NOT NULL, chunk_count INTEGER DEFAULT 0, uploaded_at TEXT NOT NULL), `session_library_attachments` table (session_id TEXT FK CASCADE, library_id TEXT FK CASCADE, attached_at TEXT NOT NULL, PK session_id). Index on `documents(library_id)`.
- `backend/app/models/db.py` — add `DocumentLibrary`, `Document`, `SessionLibraryAttachment` ORM models
- `backend/app/models/enums.py` — add `ActionType` values: `doc_upload`, `doc_delete`, `library_create`, `library_delete`, `library_attach`, `library_detach`
- `backend/app/models/schemas.py` — add Phase 3 schemas: `DocumentLibraryCreate`, `DocumentLibraryResponse`, `DocumentResponse`, `DocumentUploadResponse`, `LibraryAttachRequest`, `ChunkMetadata`, `DocumentChunk`, `DocumentRetrievalResult`
- `backend/app/services/documents/library_service.py` — `list_all()`, `get(id)`, `create(name)`, `delete(id)` (also deletes ChromaDB collection), `add_document(library_id, filename, file_hash, parse_tier, chunk_count)`, `remove_document(library_id, doc_id)`, `attach_to_session(session_id, library_id)`, `detach_from_session(session_id)`, `get_attached_library(session_id)`, `update_stats(library_id)` (recomputes doc_count, chunk_count, parse_quality)
- `backend/tests/unit/test_library_service.py` — CRUD, attach/detach, stats recompute, delete cascades

**Verify:** `pytest tests/unit/test_library_service.py -x -v`

### Run 13.3: Documents Router, API Tests, Dependency Wiring
- `backend/app/routers/documents.py` — `GET /documents/libraries` (list all), `POST /documents/libraries` (201, create), `DELETE /documents/libraries/{id}` (delete + vectors), `POST /documents/libraries/{id}/upload` (UploadFile, multipart), `DELETE /documents/libraries/{id}/docs/{did}` (remove document), `POST /documents/libraries/{id}/attach` (attach to session), `POST /documents/libraries/detach` (detach from session). All envelope-wrapped. Guardrail: 50MB upload size, 100 docs per library.
- `backend/app/dependencies.py` — add `get_chromadb(request)` from `app.state`, returns None if unconfigured (same soft-dep pattern as `get_openrouter`). Add `get_embedding_service(request)`.
- `backend/app/main.py` — include documents router at `/api/v1/documents`. Lifespan: create ChromaDB client + EmbeddingService on `app.state`. Health reports `vector_store` status (`ready` | `unconfigured` | `degraded`).
- `backend/tests/api/test_document_endpoints.py` — list empty, create library, upload file (mock ingestion), delete doc, delete library, attach/detach, upload too large → 400, too many docs → 409
- `backend/app/services/guardrails.py` — extend: `MAX_DOC_UPLOAD_SIZE_MB = 50`, `MAX_DOCS_PER_LIBRARY = 100`, `check_doc_upload(file_size, library_doc_count)`

**Verify:** `pytest tests/api/test_document_endpoints.py -x -v`, `pytest tests/ -x -v`

---

## Stage 14 — Ingestion Pipeline (3 runs)

### Run 14.1: Raw Fallback Parser + Chunking Service
- `backend/app/services/documents/parsers/__init__.py` — package init
- `backend/app/services/documents/parsers/base.py` — `ParseResult` dataclass (text: str, sections: list[Section] | None, parse_tier: str). `Section` dataclass (heading: str | None, content: str, page_number: int | None).
- `backend/app/services/documents/parsers/raw_parser.py` — `RawParser.parse(file_path: Path, mime_type: str) -> ParseResult`. Uses `PyPDF2` for PDF, `python-docx` for DOCX. Returns `parse_tier="basic"`. Plain text extraction only.
- `backend/app/services/documents/chunking.py` — `ChunkingService.chunk(parse_result: ParseResult, chunk_size: int = 512, overlap: int = 64) -> list[Chunk]`. `Chunk` dataclass (text: str, index: int, page_number: int | None, section_heading: str | None, parse_tier: str). Recursive splitting: paragraph → sentence → word boundary. Token counting via `tiktoken` or simple whitespace-split approximation.
- `backend/tests/unit/test_raw_parser.py` — parse simple PDF (fixture), parse DOCX, unsupported type raises ValueError
- `backend/tests/unit/test_chunking.py` — short text returns single chunk, long text splits respecting overlap, metadata preserved, empty text returns empty list

**Verify:** `pytest tests/unit/test_raw_parser.py tests/unit/test_chunking.py -x -v`

### Run 14.2: Unstructured Parser (Tier 2)
- `backend/app/services/documents/parsers/unstructured_parser.py` — `UnstructuredParser.parse(file_path: Path, mime_type: str) -> ParseResult`. Uses `unstructured` library: `partition_pdf()` / `partition_docx()`. Maps element types (Title, NarrativeText, ListItem, Table) to sections. Returns `parse_tier="standard"`. Catches exceptions → raises `ParseError` (callers fall through to next tier).
- `backend/tests/unit/test_unstructured_parser.py` — mock `unstructured.partition_pdf`: elements → sections, table handling, failure raises ParseError
- `backend/tests/fixtures/sample_doc.pdf` — small test PDF fixture (if not already present)

**Verify:** `pytest tests/unit/test_unstructured_parser.py -x -v`

### Run 14.3: Docling Parser (Tier 1) + Tiered Pipeline Orchestrator
- `backend/app/services/documents/parsers/docling_parser.py` — `DoclingParser.parse(file_path: Path, mime_type: str) -> ParseResult`. Uses `docling` library for structural extraction: headings, tables, lists, reading order. Returns `parse_tier="high"`. Catches exceptions → raises `ParseError`.
- `backend/app/services/documents/ingestion.py` — `IngestionService.ingest(library_id: str, file_path: Path, filename: str, mime_type: str) -> DocumentUploadResponse`. Pipeline: compute SHA-256 hash → check dedup (same hash in library → delete old chunks) → try Docling → try Unstructured → try Raw → chunk → embed → store in ChromaDB → update SQLite (document + library stats). Returns parse tier, chunk count.
- `backend/tests/unit/test_docling_parser.py` — mock docling: structured output → sections with headings, failure raises ParseError
- `backend/tests/unit/test_ingestion.py` — mock all parsers + ChromaDB + embeddings: tier 1 success, tier 1 fail → tier 2, all fail → error, dedup replaces chunks, hash computation, stats updated

**Verify:** `pytest tests/unit/test_ingestion.py tests/unit/test_docling_parser.py -x -v`

---

## Stage 15 — Document Retrieval & Pipeline Integration (3 runs)

### Run 15.1: Vector Search Service
- `backend/app/services/documents/retrieval.py` — `DocumentRetrievalService.retrieve(query: str, library_id: str, top_k: int = 5) -> list[DocumentChunk]`. Embeds query → ChromaDB `query()` on library collection → maps results to `DocumentChunk` with metadata (document_id, page_number, section_heading, parse_tier, similarity_score).
- `backend/tests/unit/test_document_retrieval.py` — mock embeddings + ChromaDB: returns top-k chunks ordered by score, empty collection → empty results, metadata mapped correctly

**Verify:** `pytest tests/unit/test_document_retrieval.py -x -v`

### Run 15.2: Cross-Encoder Reranker
- `backend/app/services/documents/reranker.py` — `RerankerService.rerank(query: str, chunks: list[DocumentChunk], top_k: int = 3) -> list[DocumentChunk]`. Uses `sentence-transformers` `CrossEncoder` (`cross-encoder/ms-marco-MiniLM-L-6-v2`). Re-scores chunks, returns top reranker-k sorted by new score. Lazy model loading.
- `backend/tests/unit/test_reranker.py` — mock CrossEncoder: reranks correctly, fewer chunks than top_k returns all, empty input returns empty

**Verify:** `pytest tests/unit/test_reranker.py -x -v`

### Run 15.3: Pipeline Integration (Router + Retrieval + Synthesiser Wiring)
- `backend/app/services/copilot/document_retrieval.py` — `DocumentRetrievalRole.retrieve(intent: RouterIntent, library_id: str, retrieval_service: DocumentRetrievalService, reranker_service: RerankerService, top_k: int, reranker_top_k: int) -> tuple[list[DocumentChunk], list[EvidenceSource]]`. Called when `intent.needs_docs == True` and a library is attached.
- `backend/app/services/copilot/pipeline.py` — update: after Router, check `needs_docs` + session library attachment → parallel `asyncio.gather` of graph retrieval + document retrieval. Pass doc chunks to Synthesiser as additional context. Re-retrieval on low confidence: increase doc top-k by 5 (alongside graph hop+1).
- `backend/app/services/copilot/prompts.py` — update `SYNTHESISER_SYSTEM_PROMPT`: add document context section, citation format for doc chunks (document filename, page number, chunk index).
- `backend/app/services/copilot/synthesiser.py` — update: accept `doc_chunks` param, include in prompt context, emit `evidence` events with doc chunk sources.
- `backend/app/services/guardrails.py` — extend: `DOC_RETRIEVAL_TOP_K = 5` (soft, max 20), `RERANKER_TOP_K = 3` (soft, max 10) to SOFT_LIMITS.
- `backend/tests/unit/test_document_retrieval_role.py` — mock services: retrieval + rerank → evidence sources, no library → skipped, needs_docs=False → skipped
- `backend/tests/unit/test_pipeline_with_docs.py` — mock all: query with docs → graph + doc retrieval parallel → synthesiser gets both, re-retrieval increases doc top-k

**Verify:** `pytest tests/unit/test_document_retrieval_role.py tests/unit/test_pipeline_with_docs.py -x -v`

---

## Stage 16 — Frontend Document Library (3 runs)

### Run 16.1: Types, API Callers, Store Slice
- `frontend/src/lib/types.ts` — add: `DocumentLibrary`, `DocumentInfo`, `DocumentUploadResponse`, `DocumentChunk`, `ChunkMetadata`, `LibraryAttachRequest`
- `frontend/src/lib/constants.ts` — add `MAX_DOC_UPLOAD_SIZE_MB`, `MAX_DOCS_PER_LIBRARY`, `PARSE_QUALITY_TIERS`
- `frontend/src/api/documents.ts` — `listLibraries()`, `createLibrary(name)`, `deleteLibrary(id)`, `uploadDocuments(libraryId, files)` (multipart FormData), `removeDocument(libraryId, docId)`, `attachLibrary(libraryId, sessionId)`, `detachLibrary()`
- `frontend/src/store/documentSlice.ts` — `libraries[]`, `attachedLibraryId`, `isUploading`, `uploadProgress`. Actions: `loadLibraries`, `addLibrary`, `removeLibrary`, `setAttachedLibrary`, `clearAttachedLibrary`, `startUpload`, `finishUpload`.
- `frontend/src/store/index.ts` — wire `DocumentSlice`

**Verify:** `npx tsc --noEmit`

### Run 16.2: DocumentLibrary Panel, Upload, Attach/Detach
- `frontend/src/components/documents/DocumentLibraryPanel.tsx` — Navigator tab: lists library entries (name, doc count, chunk count, relative timestamp, parse quality tier badge, attached indicator). Create library button + name input. Delete library (with confirmation). Attach/detach toggle per entry (only one attached at a time).
- `frontend/src/components/documents/DocumentUpload.tsx` — drag-and-drop + file picker inside library detail view. Accepts PDF/DOCX. Shows upload progress. File size validation (50MB). Displays per-document parse tier after upload completes. Re-upload replaces (SHA-256 dedup handled by backend).
- `frontend/src/components/navigator/Navigator.tsx` — update: add "Documents" tab rendering DocumentLibraryPanel
- `frontend/src/hooks/useDocumentActions.ts` — bridge between UI and API+store: `createLibrary`, `deleteLibrary`, `uploadFiles`, `removeDocument`, `attachLibrary`, `detachLibrary`. Error handling → uiSlice banners.

**Verify:** `npx tsc --noEmit`

### Run 16.3: Citation Rendering, Vector Store Status, Tests
- `frontend/src/components/copilot/EvidencePanel.tsx` — update: render document chunk evidence alongside graph evidence. Show filename, page number, section heading, parse tier badge. Chunk text preview (truncated). Click → no canvas action (docs aren't graph elements), but highlight chunk in list.
- `frontend/src/components/layout/Toolbar.tsx` — update: add vector store status indicator (green dot = ready, grey = unconfigured, red = degraded). Show attached library name when present.
- `frontend/src/store/monitoringSlice.ts` — update: add `vectorStoreStatus` from health endpoint
- `frontend/src/hooks/useHealthPolling.ts` — update: parse `vector_store` status from health response
- `frontend/tests/documents/documentSlice.test.ts` — slice lifecycle: load, add, remove, attach, detach, upload state
- `frontend/tests/documents/DocumentLibraryPanel.test.tsx` — renders empty, renders libraries, create, delete, attach

**Verify:** `npm test -- --run`, `npx tsc --noEmit`

---

## Stage 17 — Integration & Polish (2 runs)

### Run 17.1: Full Wiring, Action Logging, Copilot UI Updates
- `frontend/src/components/copilot/CopilotPanel.tsx` — update: show document retrieval status in pipeline indicator (`retrieving_docs`). Display mixed evidence (graph + doc) in responses.
- `frontend/src/store/copilotSlice.ts` — update: handle `doc_evidence` SSE events, merge with graph evidence
- `frontend/src/components/copilot/ConfidenceBadge.tsx` — update: tooltip includes "document-grounded" when doc evidence present
- `frontend/src/App.tsx` — wire document library loading on mount, restore attached library from session
- `backend/app/routers/documents.py` — ensure action logging for all endpoints: `library_create`, `library_delete`, `doc_upload`, `doc_delete`, `library_attach`, `library_detach`
- `backend/app/services/copilot/sse.py` — add `doc_evidence` event type alongside existing `evidence`
- `backend/app/models/schemas.py` — add `session_id` field to upload/attach requests for action logging (same pattern as graph endpoints)

**Verify:** `npx tsc --noEmit`, `pytest tests/ -x -v`

### Run 17.2: Docker, Env, Integration Tests, README
- `backend/pyproject.toml` — add Phase 3 deps to main: `chromadb>=0.5,<1`, `sentence-transformers>=3,<4`, `docling>=2,<3`, `unstructured[pdf,docx]>=0.16,<1`, `PyPDF2>=3,<4`, `python-docx>=1,<2`
- `docker-compose.yml` — add `chromadb` service (image: `chromadb/chroma:latest`, port 127.0.0.1:8100:8000, volume `chroma-data`), backend `depends_on: chromadb`. Add `CHROMA_HOST`, `CHROMA_PORT`, `EMBEDDING_MODEL` env passthrough.
- `.env.example` — add Phase 3 vars with descriptions
- `README.md` — add Phase 3 section (Document Library setup, ChromaDB, supported file types, parse quality tiers, attach/detach workflow)
- `backend/tests/unit/test_full_ingestion_integration.py` — all services mocked: upload → parse → chunk → embed → store → query → rerank → synthesise with doc context
- `frontend/tests/documents/integration.test.ts` — simulate: load libraries → attach → copilot query → doc evidence appears → detach
- Export updates: `backend/app/utils/export.py` — add `vector_manifest.json` to session export (library entry name, document list — reference only, not the documents themselves)

**Verify:** `pytest tests/ -x -v`, `npm test -- --run`, `docker compose up --build`, manual E2E

---

## Run Dependency Graph

```
13.1 → 13.2 → 13.3 ──────────────────────────────────────────┐
  │     │                                                      │
  │     └──→ 16.1 → 16.2 → 16.3 ────────────────────────────┤
  │                                                            │
  └──→ 14.1 → 14.2 → 14.3 → 15.1 → 15.2 → 15.3 ───────────┤
                                                               │
                                                         17.1 → 17.2
```

**Parallel streams after Run 13.2:**
- **Stream A (backend pipeline):** 14.1 → 14.2 → 14.3 → 15.1 → 15.2 → 15.3
- **Stream B (frontend):** 16.1 → 16.2 → 16.3 (starts once 13.2 lands schemas)
- **Stream C (documents API):** 13.3 (parallel with 14.x)
- **Merge:** Stage 17 requires all streams complete.

## Commit Convention

Each run commits as: `ph3-stage-N.R: brief description` (e.g., `ph3-stage-13.1: chromadb client, embedding service, config extension`)

## Total: 14 runs across 5 stages (Stages 13–17)
