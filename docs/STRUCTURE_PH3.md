G-Lab — STRUCTURE_PH3.md
=========================

> **Status:** v1.0 — March 2026
> **Ownership:** This document defines _where_ to start and _in what order_ to build Phase 3. `PRODUCT.md` defines what and why. `ARCHITECTURE.md` defines how and holds all canonical schemas (§14). `IMPLEMENTATION_PLAN_PH3.md` holds granular per-run file lists and verify steps.
> **Scope:** Phase 3 only. Phase 1 (Stages 1–7) and Phase 2 (Stages 8–12) are complete.

* * *

## 1. Build Order

Build proceeds in **5 stages** (Stages 13–17, continuing from Phase 2). Each stage produces a runnable or testable increment. Dependencies flow downward — never start a stage until its prerequisites are done.

```
Stage 13: Document Infrastructure (ChromaDB, schemas, library CRUD)
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
Stage 14: Ingestion Pipeline     Stage 16: Frontend Document Library
  (parsers, chunking,              (slices, API callers,
   embedding, orchestrator)         panels, upload UI)
    │                                  │
    ▼                                  │
Stage 15: Document Retrieval           │
  (vector search, reranker,            │
   copilot pipeline wiring)            │
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
             Stage 17: Integration & Polish
```

**Parallel work streams:**

- **Stream A (backend pipeline):** Stages 14–15. Full ingestion + retrieval pipeline without touching React.
- **Stream B (frontend):** Stage 16 starts when Stage 13 is done (needs schemas + types). Mock document data.
- **Stream C (documents API):** Run 13.3 can proceed in parallel with Stage 14.
- **Merge:** Stage 17 requires all three streams complete.

* * *

### Stage 13 — Document Infrastructure

**Goal:** ChromaDB client works, embedding service initialised, document library CRUD operational, upload endpoint accepts files, attach/detach wired.

**Depends on:** Phase 2 complete.

**Runs:** 3

**Files:**

1. `backend/app/services/documents/chromadb_client.py` — Async ChromaDB HTTP client wrapper: connect, collection CRUD, add/query/delete documents
2. `backend/app/services/documents/embeddings.py` — Embedding service using `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dims). Lazy loading.
3. `backend/app/config.py` — Extend Settings with `CHROMA_HOST`, `CHROMA_PORT`, `EMBEDDING_MODEL`
4. `backend/alembic/versions/003_add_document_libraries.py` — `document_libraries`, `documents`, `session_library_attachments` tables
5. `backend/app/models/db.py` — `DocumentLibrary`, `Document`, `SessionLibraryAttachment` ORM models
6. `backend/app/models/schemas.py` — Phase 3 schemas: `DocumentLibraryCreate/Response`, `DocumentResponse`, `DocumentUploadResponse`, `LibraryAttachRequest`, `ChunkMetadata`, `DocumentChunk`, `DocumentRetrievalResult`
7. `backend/app/services/documents/library_service.py` — Library CRUD, document tracking, attach/detach, stats recomputation
8. `backend/app/routers/documents.py` — 7 endpoints at `/api/v1/documents` (list, create, delete, upload, remove doc, attach, detach). Guardrails: 50MB upload, 100 docs per library.
9. `backend/app/dependencies.py` — `get_chromadb`, `get_embedding_service` dependencies
10. `backend/app/main.py` — Wire documents router, create ChromaDB + embedding service in lifespan, health reports `vector_store` status
11. `backend/app/services/guardrails.py` — Extend: `MAX_DOC_UPLOAD_SIZE_MB`, `MAX_DOCS_PER_LIBRARY`, `check_doc_upload()`

**Test:** `pytest tests/unit/test_chromadb_client.py tests/unit/test_embeddings.py tests/unit/test_library_service.py`, `pytest tests/api/test_document_endpoints.py`

**Acceptance:** `GET /documents/libraries` returns empty list. Create library → upload doc → attach to session → detach. Upload > 50MB → 400. Health shows `vector_store` status.

* * *

### Stage 14 — Ingestion Pipeline

**Goal:** Three-tier document parse pipeline works end-to-end: Docling → Unstructured → Raw fallback. Chunking produces embeddings stored in ChromaDB. Parse quality tiers tracked.

**Depends on:** Stage 13 (ChromaDB client, embedding service).

**Runs:** 3

**Files:**

1. `backend/app/services/documents/parsers/base.py` — `ParseResult` and `Section` dataclasses
2. `backend/app/services/documents/parsers/raw_parser.py` — Tier 3: PyPDF2 (PDF) + python-docx (DOCX). Plain text, no structure. `parse_tier="basic"`.
3. `backend/app/services/documents/parsers/unstructured_parser.py` — Tier 2: `unstructured` library partition. Text blocks with element types. `parse_tier="standard"`.
4. `backend/app/services/documents/parsers/docling_parser.py` — Tier 1: `docling` structural extraction. Headings, tables, lists, reading order. `parse_tier="high"`.
5. `backend/app/services/documents/chunking.py` — Recursive character splitting: 512 tokens, 64 overlap. Paragraph → sentence → word boundary. Metadata preserved per chunk.
6. `backend/app/services/documents/ingestion.py` — `IngestionService.ingest()` — orchestrates: SHA-256 dedup → Docling → Unstructured → Raw → chunk → embed → ChromaDB store → SQLite update. Returns parse tier + chunk count.

**Test:** Unit tests per parser (mocked libs), chunking logic tests, ingestion orchestrator tests (mocked parsers + services): tier fallthrough, dedup, stats update.

**Acceptance:** Upload a PDF → Docling parses it (or falls through). Chunks stored in ChromaDB. Re-upload same file → old chunks replaced. Library stats updated.

* * *

### Stage 15 — Document Retrieval & Pipeline Integration

**Goal:** Vector search returns relevant chunks. Cross-encoder reranker improves precision. Copilot pipeline consumes document context alongside graph data. Re-retrieval increases doc top-k.

**Depends on:** Stage 14 (ingestion pipeline), Stage 13 (ChromaDB client).

**Runs:** 3

**Files:**

1. `backend/app/services/documents/retrieval.py` — `DocumentRetrievalService.retrieve()` — embed query → ChromaDB search → map to `DocumentChunk` with similarity scores
2. `backend/app/services/documents/reranker.py` — `RerankerService.rerank()` — cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) re-scores chunks, returns top reranker-k
3. `backend/app/services/copilot/document_retrieval.py` — `DocumentRetrievalRole.retrieve()` — called when `needs_docs=True` + library attached. Returns chunks + evidence sources.
4. `backend/app/services/copilot/pipeline.py` — Update: parallel `asyncio.gather` of graph + doc retrieval. Doc chunks passed to synthesiser. Re-retrieval increases doc top-k by 5.
5. `backend/app/services/copilot/prompts.py` — Update: synthesiser prompt includes document context section + citation format
6. `backend/app/services/copilot/synthesiser.py` — Update: accepts `doc_chunks`, emits doc-sourced evidence events
7. `backend/app/services/guardrails.py` — Extend: `DOC_RETRIEVAL_TOP_K`, `RERANKER_TOP_K` soft limits

**Test:** Unit tests per service (mocked ChromaDB + embeddings): vector search, reranking, document retrieval role, pipeline with docs, re-retrieval flow.

**Acceptance:** Copilot query with attached library → retrieves doc chunks → synthesiser cites them. Low confidence → re-retrieval with top-k + 5.

* * *

### Stage 16 — Frontend Document Library

**Goal:** Document Library UI in Navigator. Upload, manage, attach/detach libraries. Vector store status visible. Document evidence renders in Inspector.

**Depends on:** Stage 13 (schemas/types). Can proceed in parallel with Stages 14–15 using mock data.

**Runs:** 3

**Files:**

1. `frontend/src/lib/types.ts` — Phase 3 types: `DocumentLibrary`, `DocumentInfo`, `DocumentUploadResponse`, `DocumentChunk`, `ChunkMetadata`, `LibraryAttachRequest`
2. `frontend/src/api/documents.ts` — Library CRUD, upload (FormData), attach/detach API callers
3. `frontend/src/store/documentSlice.ts` — Libraries, attached library, upload state + actions
4. `frontend/src/store/index.ts` — Wire `DocumentSlice`
5. `frontend/src/components/documents/DocumentLibraryPanel.tsx` — Navigator tab: library list (name, counts, quality tier, attachment status), create/delete, attach/detach
6. `frontend/src/components/documents/DocumentUpload.tsx` — Drag-and-drop + file picker, progress, size validation, parse tier display
7. `frontend/src/hooks/useDocumentActions.ts` — Bridge: create, delete, upload, attach, detach → API + store + error banners
8. `frontend/src/components/navigator/Navigator.tsx` — Update: add "Documents" tab
9. `frontend/src/components/copilot/EvidencePanel.tsx` — Update: render document chunk evidence (filename, page, section, tier badge, text preview)
10. `frontend/src/components/layout/Toolbar.tsx` — Update: vector store status indicator + attached library name
11. `frontend/src/store/monitoringSlice.ts` — Update: `vectorStoreStatus` from health
12. `frontend/src/hooks/useHealthPolling.ts` — Update: parse `vector_store` status

**Test:** `documentSlice.test.ts` (slice lifecycle), `DocumentLibraryPanel.test.tsx` (renders, create, delete, attach).

**Acceptance:** Documents tab in Navigator. Upload PDFs/DOCX. Attach library to session. Vector store indicator in Toolbar. Document evidence shows in Inspector alongside graph evidence.

* * *

### Stage 17 — Integration & Polish

**Goal:** Full investigation flow with document grounding. Mixed graph + doc evidence. Docker ready with ChromaDB. Export includes vector manifest.

**Depends on:** Stages 15 + 16.

**Runs:** 2

**Files:**

1. `frontend/src/components/copilot/CopilotPanel.tsx` — Update: document retrieval status in pipeline indicator, mixed evidence display
2. `frontend/src/store/copilotSlice.ts` — Update: handle `doc_evidence` SSE events
3. `frontend/src/App.tsx` — Wire document library loading, restore attached library from session
4. `backend/app/routers/documents.py` — Action logging for all document endpoints
5. `backend/app/services/copilot/sse.py` — Add `doc_evidence` event type
6. `backend/app/utils/export.py` — Add `vector_manifest.json` to session export (library entry reference only)
7. `backend/pyproject.toml` — Add Phase 3 deps: `chromadb`, `sentence-transformers`, `docling`, `unstructured[pdf,docx]`, `PyPDF2`, `python-docx`
8. `docker-compose.yml` — Add `chromadb` service, backend `depends_on`, env vars
9. `.env.example` — Phase 3 vars with descriptions
10. `README.md` — Phase 3 section (Document Library, ChromaDB, supported formats, parse tiers)

**Test:** Full backend suite + full frontend suite. `docker compose up --build`. Manual E2E: upload document → attach library → ask Copilot question → see document-grounded response with citations → both graph and doc evidence in Inspector.

**Acceptance:** Phase 3 validation criteria met — user can corroborate a graph-derived finding against an uploaded document and see both sources cited in a single Copilot response.

* * *

## 2. Phase 1 + 2 Infrastructure Reused

Phase 3 builds on — but does not restructure — these prior-phase components:

| Prior Component                    | Phase 3 Usage                                              |
| ---------------------------------- | ---------------------------------------------------------- |
| `app/services/guardrails.py`       | Extended with doc upload + retrieval soft limits            |
| `app/services/copilot/pipeline.py` | Extended: parallel doc retrieval alongside graph retrieval  |
| `app/services/copilot/prompts.py`  | Synthesiser prompt gains document context section           |
| `app/services/copilot/synthesiser.py` | Accepts doc chunks, emits doc evidence events           |
| `app/services/copilot/sse.py`      | New `doc_evidence` event type alongside existing types     |
| `app/services/action_log.py`       | Logs document library + upload actions                     |
| `app/core/cache.py`               | `@cached` for embedding model registry (if needed)         |
| `store/copilotSlice.ts`           | Extended: doc evidence in responses                        |
| `components/copilot/EvidencePanel.tsx` | Extended: renders doc chunk citations                  |
| `hooks/useHealthPolling.ts`        | Extended: parses `vector_store` status                     |

* * *

## 3. Key Design Decisions

| Decision                         | Chosen                                 | Rationale                                                           |
| -------------------------------- | -------------------------------------- | ------------------------------------------------------------------- |
| Vector store                     | ChromaDB (self-hosted sidecar)         | Embeds model locally, no external API for indexing, simple client   |
| Embedding model                  | `all-MiniLM-L6-v2` (384 dims)          | Lightweight, good quality, runs locally inside ChromaDB             |
| Parse pipeline                   | Three-tier fallback                    | Maximises coverage: structural when possible, always has fallback   |
| Tier 1 parser                    | Docling                                | Best structural extraction for headings, tables, reading order      |
| Tier 2 parser                    | Unstructured                           | Good general-purpose extraction when Docling fails                  |
| Tier 3 parser                    | PyPDF2 / python-docx (raw)             | Always works, but no structure preserved                            |
| Reranker                         | Cross-encoder (`ms-marco-MiniLM-L-6-v2`) | Lightweight, improves precision without heavy compute            |
| Library scoping                  | Workspace-scoped, not session-scoped   | Libraries persist across sessions, one attachment at a time         |
| Deduplication                    | SHA-256 hash per document              | Re-upload replaces chunks, prevents duplicates                     |
| Pipeline integration             | Parallel graph + doc retrieval          | Minimises latency — both retrievals run concurrently               |

* * *

## 4. New Environment Variables

| Variable          | Required | Default            |
| ----------------- | -------- | ------------------ |
| `CHROMA_HOST`     | No       | `chromadb`         |
| `CHROMA_PORT`     | No       | `8000`             |
| `EMBEDDING_MODEL` | No       | `all-MiniLM-L6-v2` |

* * *

## 5. Commit Convention

Format: `ph3-stage-N.R: description` (e.g., `ph3-stage-13.1: chromadb client, embedding service, config extension`)

Progress derived from git history:
```bash
git log --oneline --grep='ph3-stage-'        # all Phase 3 runs
git log --oneline --grep='ph3-stage-N.'      # runs for stage N
```

## Total: 14 runs across 5 stages (Stages 13–17)
