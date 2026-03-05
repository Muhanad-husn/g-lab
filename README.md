# G-Lab

**Graph investigation workbench for data journalists and OSINT investigators.**

G-Lab is a self-hosted, local, session-based environment for exploring graph databases with optional AI assistance. The graph canvas is the core product — AI is a sidecar. All data stays on your machine; no telemetry, no proxied credentials.

---

## Who It's For

- **Data journalists** tracing ownership chains, mapping influence networks, corroborating sources against documents.
- **OSINT investigators** conducting deep network tracing and hypothesis testing.

---

## Design Principles

1. **User drives, AI assists** — every graph mutation is initiated or approved by the user.
2. **Progressive disclosure** — productive in under 5 minutes with just the canvas; AI and advanced config reveal themselves as needed.
3. **Reproducibility by default** — every session is exportable and every action is logged.
4. **Privacy through architecture** — fully self-hosted; nothing leaves the host.

---

## Tech Stack

| Layer          | Technology                                     |
| -------------- | ---------------------------------------------- |
| Frontend       | React 18 + TypeScript, Vite, Zustand, Tailwind |
| Graph renderer | Cytoscape.js + CoSE-Bilkent layout             |
| UI components  | shadcn/ui                                      |
| Backend        | FastAPI (Python 3.12), Uvicorn                 |
| Graph DB       | Neo4j (user-managed, read-only connection)     |
| Session store  | SQLite (embedded, WAL mode)                    |
| LLM gateway    | OpenRouter (Phase 2)                           |
| Vector store   | ChromaDB (Phase 3)                             |

---

## Prerequisites

- Docker & Docker Compose
- A running Neo4j instance (G-Lab connects **read-only** — you manage Neo4j separately)
- Node.js 20+ and Python 3.12+ (for local development without Docker)

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> g-lab && cd g-lab

# 2. Configure environment
cp .env.example .env
# Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# 3. Run
docker compose up
```

| Service  | URL                    |
| -------- | ---------------------- |
| Frontend | http://localhost:5173  |
| Backend  | http://localhost:8000  |

---

## Development

```bash
# Backend — lint, type-check, tests
cd backend
ruff check app/ --fix && ruff format app/
mypy app/
pytest tests/unit/ -x -v

# Frontend — lint, type-check, tests
cd frontend
npx eslint src/ --fix && npx prettier --write src/
npx tsc --noEmit
npm test -- --run

# E2E
docker compose -f docker-compose.test.yml up
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Host Machine (Docker Compose)                       │
│                                                      │
│  Frontend :5173 ──▶ Backend :8000 ──▶ Neo4j (yours) │
│                          │                           │
│                     SQLite (sessions, logs)          │
│                     ChromaDB :8100  ← Phase 3        │
│                          │                           │
│                     OpenRouter      ← Phase 2        │
└──────────────────────────────────────────────────────┘
```

Key constraints:
- Neo4j access is **read-only**. G-Lab never writes to your graph.
- All API endpoints follow the envelope format: `{ data, warnings, meta }` on success.
- Canvas hard limit: **500 nodes**.

---

## AI Copilot (Phase 2)

G-Lab includes an optional AI Copilot that can answer questions about your graph, generate Cypher queries, and propose graph expansions — all via a streaming chat panel.

### Setup

1. Get an API key from [OpenRouter](https://openrouter.ai) (free tier available).
2. Add it to your `.env`:

   ```
   OPENROUTER_API_KEY=sk-or-...
   ```

3. Restart the stack: `docker compose up`.

The Copilot status dot in the toolbar turns green when the key is valid. No key = Copilot panel disabled; the rest of G-Lab works normally.

### How It Works

| Stage       | What happens                                                         |
| ----------- | -------------------------------------------------------------------- |
| **Routing** | Classifies your query: needs graph data? needs documents?            |
| **Retrieval** | Generates and runs a safe read-only Cypher query against your Neo4j |
| **Synthesis** | Streams a grounded answer with confidence score and evidence links  |
| **Delta** | Proposes new nodes/edges to add to the canvas (Accept or Discard)   |

Re-retrieval triggers automatically if confidence is below 40%.

### Presets & Advanced Mode

Presets bundle model assignments and token budgets. Three system presets are seeded at startup:

| Preset      | Router model         | Synthesis model       | Use case             |
| ----------- | -------------------- | --------------------- | -------------------- |
| **Fast**    | claude-3-haiku       | claude-3-haiku        | Quick questions       |
| **Balanced**| claude-3-haiku       | claude-3-sonnet       | Default              |
| **Thorough**| claude-3-sonnet      | claude-3-opus         | Deep investigations  |

Toggle **Advanced Mode** in the toolbar to assign individual models per pipeline stage and tune token budgets.

---

## Document Library (Phase 3)

G-Lab can ground Copilot answers in your own documents — PDFs and DOCX files stored locally in ChromaDB.

### Setup

ChromaDB is included in `docker-compose.yml` and starts automatically. No additional configuration is required for the default setup.

| Service  | URL                   |
| -------- | --------------------- |
| ChromaDB | http://localhost:8100 |

The vector store status dot in the toolbar turns green when ChromaDB is reachable.

### Supported File Types

| Format | Extensions         |
| ------ | ------------------ |
| PDF    | `.pdf`             |
| Word   | `.docx`            |

Maximum upload size: **50 MB** per file. Maximum **100 documents** per library.

### Parse Quality Tiers

Documents are parsed in tier order — highest quality first, falling back automatically:

| Tier         | Library            | Quality | Use case                             |
| ------------ | ------------------ | ------- | ------------------------------------ |
| **high**     | docling            | Best    | Structured PDFs with headings/tables |
| **standard** | unstructured       | Good    | General PDFs and DOCX files          |
| **basic**    | PyPDF2/python-docx | Fast    | Plain text extraction fallback       |

The parse tier badge appears on each document after upload.

### Attach/Detach Workflow

1. Open the **Documents** tab in the Navigator.
2. Create a library and upload files.
3. Click **Attach** to link the library to the current session — only one library can be attached at a time.
4. Ask the Copilot a question. When it needs documents, it automatically retrieves relevant chunks, re-ranks them, and cites them alongside graph evidence.
5. Click **Detach** to stop using the library for this session.

Session exports include a `vector_manifest.json` listing the library name and document filenames (not the document contents themselves).

---

## Roadmap

| Phase | Description                                           | Status      |
| ----- | ----------------------------------------------------- | ----------- |
| 0     | Project bootstrap — tooling, logging, cache           | Complete    |
| 1     | Core workbench — canvas, sessions, Neo4j proxy        | Complete    |
| 2     | AI Copilot — LLM-assisted query and summarisation     | Complete    |
| 3     | Document store — ChromaDB vector search, grounding    | Complete    |

---

## Documentation

| Document                        | Purpose                                           |
| ------------------------------- | ------------------------------------------------- |
| `docs/PRODUCT.md`               | What G-Lab is, who it's for, UX rules             |
| `docs/ARCHITECTURE.md`          | System design, data models, API surface           |
| `docs/IMPLEMENTATION_PLAN.md`   | Granular build plan with per-run file lists       |
| `docs/STRUCTURE_PH1.md`         | Phase 1 build order and stage breakdown           |

---

## License

_TBD_
