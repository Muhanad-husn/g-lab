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

## Roadmap

| Phase | Description                                           | Status      |
| ----- | ----------------------------------------------------- | ----------- |
| 0     | Project bootstrap — tooling, logging, cache           | Complete    |
| 1     | Core workbench — canvas, sessions, Neo4j proxy        | In progress |
| 2     | AI Copilot — LLM-assisted query and summarisation     | Planned     |
| 3     | Document store — ChromaDB vector search, findings     | Planned     |

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
