G-Lab — PRODUCT.md
==================

> **Status:** v3.0 — March 2026
> **Ownership:** This document defines _what_ G-Lab is and _why_ each decision was made. `ARCHITECTURE.md` defines _how_ it's built. No schema or technical detail lives here.

* * *

## 1. Product Identity

G-Lab is a **graph investigation workbench** — a local, session-based environment where a human investigator explores a graph database with optional AI assistance.

The graph canvas is the product. AI is a sidecar. If the AI layer were removed entirely, G-Lab should still be a useful investigation tool. If the canvas were removed, nothing remains.

**Design principles:**

1. **User drives, AI assists.** Every graph mutation is initiated or approved by the user. The Copilot proposes; the user disposes.
2. **Progressive disclosure.** A new user should be productive in under 5 minutes with just the canvas. AI, document stores, and advanced config reveal themselves as needed.
3. **Reproducibility by default.** Every session is exportable. Every action is logged. An exported session can reconstruct the full investigation on another machine.
4. **Privacy through architecture.** All data stays local. No telemetry. No proxied credentials. Self-hosted only.

* * *

## 2. Who It's For

### Primary: Data Journalists & OSINT Investigators

People who trace ownership chains, map influence networks, corroborate sources against documents, and need to show their work.

They're chosen because:

- They have a recurring workflow that maps directly to graph exploration (seed → expand → query → document → export).
- Data sensitivity makes self-hosted tooling a requirement, not a preference.
- Evidence grounding and reproducibility are professional necessities.

**Two sub-personas with one default:**

|                   | Data Journalist                   | OSINT Investigator                       |
| ----------------- | --------------------------------- | ---------------------------------------- |
| **Graph comfort** | Moderate                          | High                                     |
| **AI comfort**    | Higher                            | Lower                                    |
| **Primary task**  | Fact-checking, ownership research | Deep network tracing, hypothesis testing |
| **Default mode**  | Standard                          | Advanced                                 |

**All defaults are calibrated to the data journalist.** The OSINT investigator opts into Advanced Mode.

* * *

## 3. What the User Sees

The interface has four persistent zones. Nothing is hidden behind tabs that break spatial memory.

```
┌──────────────────────────────────────────────────────┐
│  Toolbar                                             │
│  [Session name] [Preset] [Vector Store status] [⚙]  │
├──────────────┬───────────────────────┬───────────────┤
│              │                       │               │
│  Navigator   │   Graph Canvas        │   Inspector   │
│              │                       │               │
│  - Search    │   (primary workspace) │   - Node/edge │
│  - Filters   │                       │     detail    │
│  - Saved     │                       │   - Evidence  │
│    findings  │                       │     panel     │
│              │                       │               │
├──────────────┴───────────────────────┴───────────────┤
│  Copilot Panel                                       │
│  [query input] ──────────────── [response stream]    │
└──────────────────────────────────────────────────────┘
```

**Zone responsibilities:**

**Toolbar.** Session identity, active preset, vector store attachment status, settings access. Always visible. Minimal.

**Navigator (left).** Search the graph database for seed nodes. Filter the canvas by node/edge type. Access saved durable findings from the current session.

**Graph Canvas (center).** The investigation surface. Nodes and edges render here. All expansions (manual or AI-driven) produce visible deltas on this canvas. Selection drives the Inspector. This zone gets the majority of screen real estate.

**Inspector (right).** Context-sensitive detail panel. When a node or edge is selected, shows its properties. When a Copilot response includes evidence, shows source citations (graph paths or document chunks). Collapses when nothing is selected.

**Copilot Panel (bottom).** Chat-style input for AI queries. Responses stream progressively (SSE). Each response can include a text answer, an evidence map, and a graph delta. The panel is collapsible — the canvas works without it.

**Key UX rules:**

- Graph deltas from AI actions are always highlighted before being committed to the canvas. The user sees what changed.
- The Copilot panel and manual canvas interactions never block each other. A user can expand nodes manually while waiting for an AI response.
- Canvas warnings (approaching node cap, guardrail reached) appear as non-modal banners, not dialogs.

* * *

## 4. Investigation Flow

An investigation is not strictly linear, but follows a natural arc:

**1 — Seed.** Search the graph database, pick one or more starting nodes, drop them on the canvas. Optionally load their immediate neighbors.

**2 — Explore.** Manually expand nodes by relationship type or hop count. Observe the network taking shape. Filter out noise. This phase works entirely without AI.

**3 — Query.** Ask the Copilot a question grounded in the visible graph and (optionally) attached documents. The Copilot retrieves evidence, proposes a graph delta, and streams a synthesised answer with confidence scoring. The user reviews and accepts or discards the delta.

**4 — Refine.** Apply filters, hide irrelevant nodes, highlight paths of interest, re-query with sharper questions. Phases 2–4 cycle repeatedly.

**5 — Document.** Save key findings as durable memories (with optional canvas snapshots). Export the full session. The export is a self-contained reproducibility artifact.

The canvas is the cognitive anchor throughout. AI augments phases 3–4 but is absent from phases 1, 2, and 5.

* * *

## 5. How the AI Helps

The Copilot is a **retrieve-then-synthesise** pipeline, not an autonomous agent. It answers questions by pulling evidence from two sources — the graph database and (optionally) user-uploaded documents — then composing a grounded response.

**Pipeline (simplified):**

```
User query
    │
    ▼
 Router ─── classifies intent ──┬── graph query needed?
                                 ├── document query needed?
                                 └── both?
                                      │
                        ┌─────────────┼─────────────┐
                        ▼             │             ▼
                   Graph Retrieval    │     Document Retrieval (RAG)
                   (Cypher, read-only)│     (vector search + rerank)
                        │             │             │
                        └─────────────┼─────────────┘
                                      ▼
                                  Synthesiser
                                  (grounded answer + evidence map
                                   + graph delta + confidence score)
```

Three functional roles. After composing the answer, the model self-evaluates evidence sufficiency and assigns a confidence band (high / medium / low). If confidence is low, one re-retrieval attempt is made automatically. The user is notified via a non-blocking inline indicator (e.g., "Retrieving additional evidence…") so they understand the response is being refined. A second failure returns the best available answer with an explicit low-confidence flag.

**Model assignment:** Each role (Router, Graph Retrieval, Synthesiser) can be assigned a different LLM via OpenRouter. In Standard Mode, the system picks reasonable defaults. In Advanced Mode, the user controls assignments, temperature, and context window.

**Confidence scoring** is a structured output on every Copilot response. Scores are derived from the LLM's self-assessment of evidence sufficiency. The thresholds below are starting points, intended to be tuned through real-world usage:

- **High** (>0.70): answer fully grounded in retrieved evidence.
- **Medium** (0.40–0.70): partially grounded; some claims unverified.
- **Low** (<0.40): insufficient evidence; treat with caution.

Every response includes an evidence map linking claims to their sources (graph node/edge IDs or document chunk references).

* * *

## 6. Configuration

### Standard Mode (default)

Three named presets, framed as investigation styles rather than technical parameters:

| Preset                     | Use case                    | Expansion limit  | Document retrieval depth | Model tier  |
| -------------------------- | --------------------------- | ---------------- | ------------------------ | ----------- |
| **Quick Scan**             | Fast surface check          | 1 hop, 10 nodes  | Top 3                    | Lightweight |
| **Standard Investigation** | Balanced everyday use       | 2 hops, 25 nodes | Top 5                    | Balanced    |
| **Deep Dive**              | Exhaustive, high-confidence | 3 hops, 50 nodes | Top 10                   | Strongest   |

Default on first launch: **Standard Investigation.**

The user picks a preset at session start. That's it. No other configuration is required.

### Advanced Mode

Unlocks full control over:

- Per-role model assignment (Router, Graph Retrieval, Synthesiser)
- Temperature and context window per role
- Retrieval parameters (top-k, re-ranker top-k)
- Guardrail overrides (within hard limits; see Section 7)

Presets can be saved and shared as JSON. System presets are immutable; user presets are editable and deletable.

* * *

## 7. Guardrails

Guardrails protect investigation stability and prevent runaway queries. They are enforced at both the product and architecture level.

### Hard Limits (non-overridable)

These limits cannot be changed by any user, in any mode. They exist to prevent the application from destabilising itself or the connected database.

| Guardrail                           | Hard limit     | Rationale                                              |
| ----------------------------------- | -------------- | ------------------------------------------------------ |
| **Max nodes on canvas**             | 500            | Beyond this, rendering and layout degrade.             |
| **Max hops per expansion**          | 5              | Unbounded traversals risk exponential blowup.          |
| **Max nodes per single expansion**  | 100            | Prevents a single action from flooding the canvas.     |
| **Cypher query timeout**            | 30 seconds     | Protects the Neo4j instance from long-running queries. |
| **Copilot response timeout**        | 120 seconds    | Prevents indefinitely hanging AI calls.                |
| **Max concurrent Copilot requests** | 1              | Serialised to avoid context corruption.                |
| **Max document upload size**        | 50 MB per file | Keeps ingestion tractable on local hardware.           |
| **Max documents per library entry** | 100            | Bounds vector store size per collection.               |

### Soft Limits (overridable in Advanced Mode)

These defaults are tuned for the Standard Investigation preset. Advanced Mode users can raise them up to the hard limit.

| Guardrail                    | Default | Overridable range |
| ---------------------------- | ------- | ----------------- |
| **Expansion hop count**      | 2       | 1–5               |
| **Nodes per expansion**      | 25      | 5–100             |
| **Document retrieval top-k** | 5       | 1–20              |
| **Re-ranker top-k**          | 3       | 1–10              |

### Canvas Warnings

The UI issues non-modal banner warnings at the following thresholds:

- **80% of canvas node cap** (400 nodes): "Canvas is getting crowded. Consider filtering."
- **Node cap reached** (500 nodes): "Node limit reached. Remove nodes or start a new session to continue expanding."
- **Expansion would exceed cap**: Pre-checked; the expansion is blocked with a message showing how many nodes would be added vs. how many slots remain.

* * *

## 8. Sessions & Memory

### Session Lifecycle

A session begins when the user starts or imports an investigation. It ends when the user explicitly closes it or starts a new one. The application restores the last active session on launch.

**Session restore behaviour:**

- **Corrupted session:** The application shows an error, prevents loading the corrupted session, and offers the user the option to start a new session. Corrupted session files are preserved on disk for manual recovery but are not loaded.
- **Neo4j instance unavailable:** The application shows a warning and loads the session in a **read-only review mode**. All memory layers (conversation history, investigation log, durable findings) are visible and browsable. All executable actions — expansion, search, Copilot queries, path discovery — are inactive and visually disabled. The user can export findings or wait for the connection to be restored.

**Session reset** clears the canvas and conversation history but preserves durable findings. The underlying graph database is never modified.

### Memory Layers

| Layer                | What it holds                                             | Lifespan             |
| -------------------- | --------------------------------------------------------- | -------------------- |
| **Conversation**     | Chat history, goals, clarifications                       | Session only         |
| **Investigation**    | Every action: expansions, queries, filters, Copilot calls | Session only         |
| **Durable Findings** | User-saved insights with optional canvas snapshots        | Survives session end |

Only durable findings require explicit user action to create. Conversation and investigation memory accumulate automatically and are discarded on session reset or close.

### Export

A session export is a `.g-lab-session` archive containing:

- Full graph state (nodes, edges, properties)
- Canvas layout and viewport
- Complete action log
- All durable findings (with snapshot images if present)
- Session configuration (preset, model assignments, guardrails)
- Vector store manifest (reference only — not the documents themselves)

Exports are versioned. The application validates the schema version on import and rejects incompatible versions with a clear error. 

* * *

## 9. Document Library

The Document Library is **workspace-scoped** — it persists across sessions within a single G-Lab installation. It is not session-scoped and not tied to any specific investigation.

A **library entry** is a named collection of documents. Users upload PDFs or DOCX files into a library entry. Documents are chunked, embedded, and stored in a local vector database. A session can attach to one library entry at a time, giving the Copilot's document retrieval access to that collection.

**Key behaviours:**

- **Switching library entries mid-session is supported.** The user can detach the current library entry and attach a different one at any point during an investigation. When switching, the Copilot's document retrieval context resets to the newly attached collection. Prior Copilot responses that cited documents from the previous entry remain in the conversation history with their citations intact, but those document chunks are no longer available for new queries.
- Re-uploading an existing document replaces its chunks (no duplicates).
- Deleting a library entry removes its vector data. Sessions that referenced it will show a warning on import.

### Parse Quality Tiers

Each library entry displays a **parse quality tier** so users understand the fidelity of their document processing. The tier reflects which stage of the ingestion pipeline succeeded:

| Tier         | Pipeline stage | Meaning                                                                                       |
| ------------ | -------------- | --------------------------------------------------------------------------------------------- |
| **High**     | Docling        | Full structural extraction: headings, tables, lists, and reading order preserved.             |
| **Standard** | Unstructured   | Good text extraction with basic structural awareness. Some complex layouts may lose fidelity. |
| **Basic**    | Raw fallback   | Plain text extraction only. No structural information. Tables and formatting are lost.        |

The tier is determined per document at ingestion time. A library entry shows the lowest tier among its documents (i.e., if one document fell back to raw extraction, the entry displays "Basic").

**UI must show per entry:** name, document count, chunk count, indexing timestamp (relative, e.g. "3 days ago"), parse quality tier, and attachment status relative to the current session.

* * *

## 10. Database Overview

On first connection to a Neo4j instance — and accessible at any time from the Navigator — G-Lab provides a **Database Overview** panel. This gives the user a structural understanding of the data before beginning an investigation.

**The overview includes:**

- **Schema summary:** Node labels, relationship types, and property keys present in the database.
- **Metrics:** Total node count, total relationship count, and counts per label/type.
- **Sample data:** For each node label, a preview table showing a small sample of nodes with their properties (default: 5 rows per label). For each relationship type, a sample showing source → relationship → target with properties.

**Purpose:** The Database Overview serves two roles. First, it orients the investigator — understanding what entities and relationships exist is a prerequisite for effective exploration. Second, it provides the foundation for **Phase 1 validation**: by exposing the schema, metrics, and sample data of whatever Neo4j instance is connected, G-Lab can demonstrate its value against any real dataset the user provides, rather than requiring a predefined reference investigation.

The overview is read-only and derived entirely from the connected database. It refreshes on connection and can be manually refreshed by the user.

* * *

## 11. Phased Scope

This design defines three release phases. Each phase is independently useful.

### Phase 1 — Graph Workbench (foundation)

Ship a fully functional graph investigation canvas without AI.

- Connect to Neo4j (read-only, user-managed credentials)
- Database Overview (schema, metrics, pagination scrollable data tables)
- Search, seed, expand, filter, inspect nodes and edges
- Path discovery (shortest path, bounded all-paths)
- Session lifecycle: start, restore (with graceful degradation), reset, export, import
- Durable findings with canvas snapshots
- Event logging (local NDJSON)
- Guardrail enforcement (hard limits on canvas size and query timeout)
- Docker Compose deployment

**Phase 1 is validated when** a user connects G-Lab to their own Neo4j instance, uses the Database Overview to understand the available schema, completes an investigation using manual exploration, and exports the result. Validation is database-agnostic — it succeeds against any well-formed Neo4j instance.

### Phase 2 — Copilot

Add the AI layer on top of the working canvas.

- Copilot panel with streaming responses
- Router → Graph Retrieval → Synthesiser pipeline
- Confidence scoring (LLM self-assessment, tunable thresholds) and evidence maps
- Re-retrieval with user notification on low confidence
- Graph deltas from AI queries (preview before commit)
- Configuration presets (Standard and Advanced Mode)
- Model registry and per-role assignment via OpenRouter
- Guardrail enforcement on AI-driven expansions (soft + hard limits)

**Phase 2 is validated when** the Copilot demonstrably reduces time-to-insight on an investigation compared to Phase 1 alone. The baseline is established by timing a set of representative tasks in Phase 1 (e.g., "find all shortest paths between entity A and entity B," "identify the most connected node within 2 hops of entity C") and comparing against the same tasks with Copilot assistance.

### Phase 3 — Document Grounding

Add document retrieval alongside graph retrieval.

- Document Library (workspace-scoped, named collections)
- Three-tier ingestion pipeline (Docling → Unstructured → raw fallback) with parse quality tiers
- Mid-session library entry switching
- RAG retrieval integrated into the Copilot pipeline
- Citation-ready evidence linking document chunks to Copilot answers
- Vector store status in toolbar

**Phase 3 is validated when** a user can corroborate a graph-derived finding against an uploaded document and see both sources cited in a single Copilot response.

### Explicit out-of-scope

- Multi-user / collaboration
- Graph write operations
- Cloud deployment
- Mobile layout
- Automated or scheduled investigations
- Real-time data ingestion (streaming or webhook-driven updates to the graph)
- Graph schema management (G-Lab reads the schema; it does not create, alter, or migrate it)
