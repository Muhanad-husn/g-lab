# G-Lab User Manual

**Graph Investigation Workbench for Data Journalists & OSINT Investigators**

*Version 1.0 — March 2025*

---

## Table of Contents

1. [What Is G-Lab?](#1-what-is-g-lab)
2. [Who Is It For?](#2-who-is-it-for)
3. [How It Works (The Big Picture)](#3-how-it-works-the-big-picture)
4. [Getting Started](#4-getting-started)
5. [The Interface at a Glance](#5-the-interface-at-a-glance)
6. [Sessions — Your Investigation Workspace](#6-sessions--your-investigation-workspace)
7. [Exploring the Database](#7-exploring-the-database)
8. [The Graph Canvas — Your Visual Workspace](#8-the-graph-canvas--your-visual-workspace)
9. [Searching and Adding Nodes](#9-searching-and-adding-nodes)
10. [Expanding Connections](#10-expanding-connections)
11. [Finding Paths Between Nodes](#11-finding-paths-between-nodes)
12. [Filtering What You See](#12-filtering-what-you-see)
13. [The Inspector — Reading the Details](#13-the-inspector--reading-the-details)
14. [AI Copilot — Asking Questions in Plain English](#14-ai-copilot--asking-questions-in-plain-english)
15. [Understanding Confidence Scores](#15-understanding-confidence-scores)
16. [Ghost Elements — AI Proposals on the Canvas](#16-ghost-elements--ai-proposals-on-the-canvas)
17. [Document Library — Grounding Your Investigation](#17-document-library--grounding-your-investigation)
18. [Uploading Documents](#18-uploading-documents)
19. [Findings — Saving What Matters](#19-findings--saving-what-matters)
20. [Exporting Your Work](#20-exporting-your-work)
21. [Presets and Configuration](#21-presets-and-configuration)
22. [Advanced Mode](#22-advanced-mode)
23. [Guardrails and Limits](#23-guardrails-and-limits)
24. [Status Indicators](#24-status-indicators)
25. [Troubleshooting](#25-troubleshooting)
26. [Configuration Reference](#26-configuration-reference)

---

## 1. What Is G-Lab?

G-Lab is a **local, self-hosted graph investigation workbench**. Think of it as a digital whiteboard connected to a graph database. You search for people, companies, addresses, or any entity in your database, pull them onto a visual canvas, expand their connections, ask an AI assistant questions about what you see, and save your findings — all from your browser.

**Key principles:**

- **You drive the investigation.** The AI suggests; you decide. Nothing gets added to your canvas without your approval.
- **Everything stays local.** Your data never leaves your machine. The database, the app, and your session files all run on your own hardware.
- **Reproducible.** Every action is logged. Every session can be exported and shared. Another analyst can open your `.g-lab-session` file and see exactly what you saw.

---

## 2. Who Is It For?

G-Lab serves two primary audiences:

### Data Journalists

You are comfortable with data but may be newer to graph thinking. You need to trace ownership structures, verify relationships between public figures and corporations, and fact-check claims. G-Lab's **Standard Mode** with sensible defaults gets you productive immediately.

### OSINT Investigators

You are experienced with network analysis and graph databases. You want fine-grained control over query depth, expansion limits, and model selection. G-Lab's **Advanced Mode** exposes every dial.

Both audiences share a common workflow: **Seed → Explore → Query → Refine → Document & Export.**

---

## 3. How It Works (The Big Picture)

G-Lab sits between you and a **Neo4j graph database** — a specialized database that stores entities (nodes) and their relationships (edges) as a network. Unlike a spreadsheet that stores rows, a graph database stores connections, making it ideal for investigations where "who knows whom" and "who owns what" are the central questions.

Here is what happens under the hood:

```
   You (Browser)
       │
       ▼
   ┌─────────┐       ┌─────────┐
   │ Frontend │──────▶│ Backend │──────▶ Neo4j (your graph data)
   │ React    │◀──────│ FastAPI │◀──────
   └─────────┘       └─────────┘
                          │
                          ├──────▶ SQLite (sessions, logs, findings)
                          ├──────▶ OpenRouter (AI models, optional)
                          └──────▶ ChromaDB (document search, optional)
```

- **Frontend** — What you see in the browser. Built with React. Renders the graph using a library called Cytoscape.js that specializes in interactive network visualization.
- **Backend** — A Python server (FastAPI) that handles your requests, talks to the database, enforces safety limits, and orchestrates the AI pipeline.
- **Neo4j** — The graph database you bring. G-Lab connects to it in **read-only mode** — it will never create, modify, or delete anything in your database.
- **SQLite** — A lightweight embedded database where G-Lab stores your sessions, findings, action logs, and settings. Lives inside the Docker volume.
- **OpenRouter** (optional) — A gateway to AI language models. When you ask the Copilot a question, the backend sends it through OpenRouter to an LLM.
- **ChromaDB** (optional) — A vector database for document search. When you upload PDFs or Word documents, they get chunked, embedded (converted to numerical vectors), and stored here so the AI can search them.

---

## 4. Getting Started

### Prerequisites

- **Docker and Docker Compose** installed on your machine
- **A Neo4j instance** running and populated with your data (G-Lab does not manage Neo4j for you)

### Step-by-Step Setup

**1. Clone the repository and enter the directory.**

```bash
git clone <repo-url> g-lab
cd g-lab
```

**2. Create your environment file.**

```bash
cp .env.example .env
```

**3. Edit `.env` with your settings.**

At minimum, you need your Neo4j connection details:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
```

For AI Copilot features, add your OpenRouter key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

**4. Start G-Lab.**

```bash
docker compose up
```

This launches three services:
| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | The app interface |
| Backend | http://localhost:8000 | API server |
| ChromaDB | http://localhost:8100 | Document vector store |

**5. Open your browser** and go to **http://localhost:5173**.

### What Happens at Startup

1. The backend tries to connect to your Neo4j instance (up to 5 attempts with increasing wait times, maxing out at 30 seconds).
2. If Neo4j is unreachable, the app starts in **degraded mode** — you can still browse existing sessions, but all graph exploration features return errors (503).
3. Database migrations run automatically (your SQLite database is created or updated).
4. The frontend loads and restores your last active session (if one exists).

---

## 5. The Interface at a Glance

When you open G-Lab, you see four zones:

```
┌──────────────────────────────────────────────────────────┐
│                    TOOLBAR (top bar)                      │
├──────────┬───────────────────────────┬───────────────────┤
│          │                           │                   │
│ NAVIGATOR│      GRAPH CANVAS         │    INSPECTOR      │
│  (left)  │       (center)            │     (right)       │
│          │                           │                   │
├──────────┴───────────────────────────┴───────────────────┤
│                 COPILOT PANEL (bottom)                    │
└──────────────────────────────────────────────────────────┘
```

- **Toolbar** — Session management, presets, connection status, settings.
- **Navigator** — A tabbed side panel on the left for database browsing, searching, filtering, managing documents, findings, and Copilot chat.
- **Graph Canvas** — The central workspace where your investigation graph lives.
- **Inspector** — A side panel on the right showing details about whatever you have selected.

Both the Navigator and Inspector can be collapsed to give the canvas more room.

---

## 6. Sessions — Your Investigation Workspace

A **session** is a self-contained investigation workspace. It stores:

- Your **canvas state** (which nodes and edges are on screen, their positions, your viewport zoom/pan)
- Your **configuration** (which preset you are using, any overrides)
- Your **conversation history** with the Copilot
- Your **findings** (notes you have saved during the investigation)
- A complete **action log** of everything you did

### Creating a Session

Click the **New Session** button in the toolbar. You will be prompted to give it a name (e.g., "Panama Papers — Shell Companies" or "Network Analysis — Subject X"). This name is for your reference only.

### Switching Sessions

Open the session menu in the toolbar. You will see your recent sessions listed. Click one to switch. Your current session is saved automatically before switching.

### Restoring on Launch

When you open G-Lab, it automatically loads the **last session you were working in**. You pick up right where you left off.

### Resetting a Session

If your canvas gets cluttered and you want a fresh start without losing your findings, use **Reset**. This clears the canvas and conversation history but **keeps all your saved findings intact**.

### Deleting a Session

Permanently removes the session and all its data. This cannot be undone.

---

## 7. Exploring the Database

Before you start pulling nodes onto your canvas, you probably want to understand what is in your database. The **Database** tab in the Navigator (the database icon) gives you an overview.

### Schema View

Shows you all the **labels** (node types) and **relationship types** in your Neo4j database, along with how many of each exist. For example:

- `Person` — 12,450 nodes
- `Company` — 8,230 nodes
- `OWNS` — 15,670 relationships
- `DIRECTOR_OF` — 4,120 relationships

### Sample Data

Click any label or relationship type to see a **sample table** with real data. This helps you understand what properties are available (e.g., a `Person` might have `name`, `date_of_birth`, `nationality`). The tables are paginated for large datasets.

This step is important because it tells you what vocabulary to use when searching. If you know your database has `Company` nodes with a `registration_number` property, you can search for specific companies by that number.

---

## 8. The Graph Canvas — Your Visual Workspace

The canvas is the heart of G-Lab. It is where your investigation takes visual form.

### How Graph Visualization Works

G-Lab uses **Cytoscape.js**, a purpose-built JavaScript library for rendering interactive network graphs. Each node appears as a circle (styled by its label/type), and each relationship appears as a line connecting two nodes.

The nodes are arranged using a **force-directed layout** (specifically the CoSE-Bilkent algorithm). Think of it like a physics simulation — nodes that are connected pull toward each other, while unconnected nodes push apart. The result is that clusters of related entities naturally group together.

### Interacting with the Canvas

| Action | What Happens |
|--------|--------------|
| **Click a node** | Selects it. Inspector shows its properties. |
| **Click an edge** | Selects it. Inspector shows its type and properties. |
| **Drag a node** | Moves it to a new position. Position is saved. |
| **Scroll wheel** | Zoom in and out. |
| **Click and drag background** | Pan the viewport. |
| **Click empty space** | Deselects everything. |

### Layout Options

You can change how nodes are arranged using the **layout selector** on the canvas toolbar:

| Layout | Best For |
|--------|----------|
| **Force-directed** (default) | General exploration. Related nodes cluster naturally. |
| **Hierarchical** | Organizational structures, ownership chains. Top-down tree. |
| **Concentric** | Showing centrality. Most-connected nodes in the center. |
| **Preset** | Restoring saved positions exactly. |

### The Node Counter

In the top-left corner of the canvas, you will see a badge showing something like **47/500**. This tells you how many nodes are on your canvas out of the maximum 500. The badge changes color as you approach the limit:

- **Gray** — Under 80%. Plenty of room.
- **Yellow** — 80-99% (400+ nodes). Consider filtering or removing nodes.
- **Red** — At the 500-node cap. You cannot add more until you remove some.

---

## 9. Searching and Adding Nodes

The **Search** tab in the Navigator (magnifying glass icon) is your primary way to seed your investigation.

### How to Search

1. Type your query in the search box (e.g., a person's name, a company registration number, an address).
2. Optionally filter by label (e.g., only search `Person` nodes).
3. Press Enter or click Search.

The backend sends a full-text search query to Neo4j and returns matching nodes.

### Adding Nodes to the Canvas

Each search result has two buttons:

- **Add** — Places the node on the canvas without expanding its connections.
- **Add + Expand** — Places the node AND immediately expands it (fetches its neighbors).

Start with **Add** if you want to be selective about what connections to explore. Use **Add + Expand** when you want to quickly see a node's immediate neighborhood.

---

## 10. Expanding Connections

Expansion is how you grow your investigation graph. You start from a seed node and progressively reveal its connections.

### How to Expand

1. **Select a node** on the canvas (click it).
2. In the canvas toolbar, set the **hop count** — how many steps away from the selected node to look.
   - **1 hop:** Direct connections only (people directly linked to this company).
   - **2 hops** (default): Connections of connections (people linked to companies linked to this company).
   - **3+ hops:** Deeper network exploration (use with caution — numbers grow fast).
3. Optionally **filter relationship types** — expand only along certain types (e.g., only `OWNS` relationships, ignoring `LOCATED_AT`).
4. Click **Expand**.

### What Happens Behind the Scenes

The backend generates a Cypher query (Neo4j's query language) based on your selection. This query is **sanitized** — it passes through an allowlist filter that only permits read operations. No data in your database can be modified.

The query runs with a **30-second timeout**. If your database is very large and the query takes too long, it will be cancelled and you will be prompted to try fewer hops or add relationship type filters.

### Expansion Limits

To keep the canvas usable, G-Lab enforces limits:

- **Per expansion:** Maximum 100 new nodes (soft default: 25, adjustable).
- **Canvas total:** Maximum 500 nodes.
- **Max hops:** Maximum 5 hops per expansion.

If an expansion would exceed the canvas cap, you will see a message like: *"Would add 45 nodes but only 12 slots remain."* You can then filter or remove nodes before trying again.

---

## 11. Finding Paths Between Nodes

One of the most powerful investigation techniques is tracing the connection path between two entities. For example: "How is Person A connected to Company B?"

### How to Find Paths

1. **Select two nodes** on the canvas (hold Ctrl/Cmd and click each one).
2. In the canvas toolbar, click **Shortest Path** or **All Shortest Paths**.
3. The backend traces routes between the two nodes (respecting the maximum hop limit from your preset).
4. The resulting path(s) appear highlighted on the canvas with all intermediate nodes and edges.

### What Is the Difference?

- **Shortest Path:** Returns one path — the shortest route between the two nodes.
- **All Shortest Paths:** Returns every path of the same minimum length. If there are three different 3-hop routes, you see all three.

This is particularly useful for revealing multiple independent connections between entities (e.g., Person A is connected to Company B through three different intermediaries).

---

## 12. Filtering What You See

As your canvas grows, it can get busy. Filters let you control visibility without deleting nodes.

### Label Filters

In the **Filters** tab of the Navigator, each node label (Person, Company, Address, etc.) has a **three-state toggle:**

1. **Visible** (eye icon) — Nodes of this type are fully shown.
2. **Collapsed** (compress icon) — Nodes of this type are compressed into a single "group" node. Useful for seeing the shape of the network without the clutter.
3. **Hidden** (no icon) — Nodes of this type are completely invisible. Their edges also disappear.

### Edge Type Filters

Each relationship type (OWNS, DIRECTOR_OF, etc.) has a **two-state toggle:**

1. **Visible** — Relationships of this type are drawn.
2. **Hidden** — Relationships of this type are invisible.

### When to Use Filters

- **Too many `Address` nodes cluttering the view?** Collapse or hide them.
- **Want to focus only on ownership relationships?** Hide all edge types except `OWNS`.
- **Looking for a specific connection pattern?** Show only the relevant labels and types.

Filters are non-destructive — the data is still on your canvas, just visually hidden. Toggle them back anytime.

---

## 13. The Inspector — Reading the Details

The **Inspector** is the right-side panel that shows detailed information about whatever you have selected on the canvas.

### When Nothing Is Selected

You will see a prompt: *"Select a node or relationship to view details."*

### When a Node Is Selected

- **Labels:** The type(s) of the node (e.g., `Person`, `PoliticallyExposedPerson`).
- **Properties:** A key-value table showing all the node's data. For example:
  - `name`: "John Smith"
  - `date_of_birth`: "1965-03-12"
  - `nationality`: "British"
  - `registration_number`: "CH-12345"

### When an Edge Is Selected

- **Type:** The relationship type (e.g., `OWNS`, `DIRECTOR_OF`).
- **Source and Target:** Which nodes it connects.
- **Properties:** Any properties on the relationship (e.g., `since`: "2010-01-01", `share_percentage`: 51).

### Evidence Tab

When the AI Copilot provides an answer, the Inspector gains an **Evidence** tab showing the sources the AI used:

- **Graph evidence:** References to specific nodes and edges, clickable to select them on the canvas.
- **Document evidence:** References to uploaded documents with filename, page number, and section heading.

---

## 14. AI Copilot — Asking Questions in Plain English

The **Copilot** is G-Lab's AI assistant. It lets you ask questions about your graph data in natural language instead of writing database queries.

> **Note:** The Copilot requires an **OpenRouter API key**. Without it, the Copilot tab is disabled.

### How to Use the Copilot

1. Open the **Copilot** tab in the Navigator (or the collapsible bottom panel).
2. Type a question in plain English, such as:
   - *"Who are the directors of companies owned by John Smith?"*
   - *"What is the shortest path between Entity A and Entity B?"*
   - *"Summarize the ownership structure of Company X."*
   - *"Are there any shared directors between these two companies?"*
3. Press Enter or click Send.

### What Happens Behind the Scenes

The Copilot runs a multi-stage pipeline:

**Stage 1 — Routing.** An AI model reads your question and classifies it:
- Does this need a graph database query?
- Does this need document search?
- What kind of Cypher query would help?
- What is the actual search query for documents?

**Stage 2 — Graph Retrieval.** If the router says the graph is needed, another AI model generates a read-only Cypher query, which is sanitized and executed against Neo4j. The results (nodes, edges, paths) become evidence.

**Stage 3 — Document Retrieval** (if a document library is attached). Your question is converted to a numerical vector (embedding) and compared against the vectors of your uploaded document chunks using ChromaDB. The most relevant chunks are further refined by a **reranker** (a specialized model that re-scores results for accuracy). The top chunks become document evidence.

**Stage 4 — Synthesis.** A final AI model receives the graph evidence, document evidence (if any), and your original question. It composes a natural language answer with citations.

### What You See During Processing

As the pipeline runs, you will see status indicators:

1. **"Routing query…"** — The AI is understanding your question.
2. **"Querying graph…"** — A database query is running.
3. **"Retrieving documents…"** — Document search is in progress (only if library attached).
4. **"Synthesising answer…"** — The AI is composing its response.

The answer streams in word by word (using Server-Sent Events, or SSE — a technique where the server pushes data to your browser in real time rather than making you wait for the complete response).

### Conversation History

The Copilot remembers your conversation within a session. You can ask follow-up questions that build on previous answers. The history is saved with the session and restored when you reopen it.

---

## 15. Understanding Confidence Scores

Every Copilot answer comes with a **confidence score** — a percentage indicating how well-grounded the answer is in actual evidence.

| Band | Score | Meaning |
|------|-------|---------|
| **High** | 70% or above | The answer is well-supported by graph data and/or documents. |
| **Medium** | 40–69% | The answer is partially supported. Some claims may be inferred. |
| **Low** | Below 40% | Limited evidence found. Treat with extra caution. |

### What Happens on Low Confidence

When the confidence is low, the Copilot automatically tries **re-retrieval** — it expands its search parameters (more hops in the graph, more document chunks) and tries again. You will see the indicator: *"Expanding retrieval…"*

This is automatic and requires no action from you. If the second attempt still yields low confidence, you will see the result with the low confidence badge and can judge for yourself.

### Document-Grounded Indicator

If the Copilot's answer uses evidence from uploaded documents (not just the graph), the confidence badge shows an additional note: **"document-grounded"**. This tells you the AI had access to your uploaded files when composing the answer.

---

## 16. Ghost Elements — AI Proposals on the Canvas

When the Copilot discovers entities or relationships that are not yet on your canvas, it proposes them as **ghost elements** — nodes and edges rendered with **dashed outlines and reduced opacity**.

Ghost elements are the AI's suggestion: *"Based on my analysis, you might want to add these to your investigation."*

### Accepting or Discarding

- **Accept:** Click the accept button on the ghost overlay. The proposed nodes/edges become permanent parts of your canvas.
- **Discard:** Click discard. The ghost elements disappear with no changes to your canvas.

This is a core design principle: **the AI suggests, you decide**. Nothing changes on your canvas without your explicit approval.

---

## 17. Document Library — Grounding Your Investigation

The Document Library (Phase 3) lets you upload PDF and Word documents so the Copilot can search them alongside the graph data. This is especially useful for:

- **Leaked documents** that contain information not yet in your database
- **Public filings** and annual reports
- **Court records** and legal documents
- **Any reference material** relevant to your investigation

### How It Works (Under the Hood)

When you upload a document, the following pipeline runs:

1. **Parsing** — The document is read and its text is extracted. G-Lab tries three parsers in order of quality:
   - **Docling** (High tier) — Full structural extraction: headings, tables, lists, reading order preserved.
   - **Unstructured** (Standard tier) — Good text with basic structure. Some complex layouts may lose fidelity.
   - **Raw** (Basic tier) — Plain text only. No formatting or structure.

   Each parser is tried in order; if one fails, the next is attempted.

2. **Chunking** — The extracted text is split into small segments (~512 tokens each, with 64-token overlap between chunks). This is because AI models work better with focused, digestible pieces of text rather than entire documents.

3. **Embedding** — Each chunk is converted into a numerical vector (a list of 384 numbers) using a model called `all-MiniLM-L6-v2`. These vectors capture the meaning of the text — chunks about similar topics will have similar vectors.

4. **Storage** — The vectors are stored in ChromaDB, a specialized database for fast vector similarity search.

5. **Deduplication** — Each document is fingerprinted with a SHA-256 hash. If you upload the same file again, it replaces the old version rather than creating duplicates.

### Managing Libraries

- **Create** — Give your library a descriptive name (e.g., "Offshore Leak Documents 2024").
- **Delete** — Removes all documents and their vector embeddings.
- **Attach to session** — Links a library to your current investigation. Each session can have one library attached at a time.
- **Detach** — Unlinks the library. Previous Copilot answers that cited documents are preserved in the chat history.
- Libraries persist across sessions — they are workspace-level, not session-level.

### Parse Quality Badges

Each document and library shows a **parse tier badge:**

- **High** — Full structure extracted (Docling succeeded)
- **Standard** — Good text, basic structure (Unstructured succeeded)
- **Basic** — Plain text only (raw fallback)

The library as a whole shows the **lowest tier** among its documents, so you know if any documents had reduced quality.

---

## 18. Uploading Documents

### Accepted Formats

- **PDF** (.pdf)
- **Microsoft Word** (.docx)

### Size Limit

50 MB per file. Up to 100 documents per library.

### How to Upload

1. Open the **Documents** tab in the Navigator.
2. Select (or create) a library.
3. Either:
   - **Drag and drop** files onto the upload area, or
   - **Click** the upload area to open a file picker.
4. Wait for ingestion to complete. You will see progress indicators and the parse tier badge once done.

### After Upload

The library panel shows each document with:
- Filename
- Parse tier badge
- Number of chunks created
- Upload timestamp

---

## 19. Findings — Saving What Matters

**Findings** are durable notes you create during your investigation. Unlike the canvas (which you might reset) and the Copilot chat (which is transient), findings survive session resets and are included in exports.

### Creating a Finding

1. Open the **Findings** tab in the Navigator.
2. Click **New Finding**.
3. Enter a **title** (e.g., "Shell company ownership chain identified").
4. Optionally write a **body** in Markdown (formatting, lists, links).
5. Optionally **capture a canvas snapshot** — a PNG of your current graph view is attached to the finding.
6. Save.

### Managing Findings

- **Edit** — Update the title or body at any time.
- **Delete** — Remove a finding permanently.
- **Download** — Export an individual finding as a Markdown file.

### What Findings Are For

Findings are your investigation's **memory**. They record conclusions, hypotheses, and observations. When you export a session, findings are included as a `findings/` folder in the ZIP archive — ready for your editor, your team, or your records.

---

## 20. Exporting Your Work

G-Lab provides three export formats, accessible from the **Export** dropdown in the toolbar.

### Session Export (.g-lab-session)

A complete, reproducible archive of your entire investigation. The file is a **ZIP archive** containing:

| File | Contents |
|------|----------|
| `manifest.json` | Export metadata (schema version, timestamp, G-Lab version) |
| `session.json` | Session name, configuration, preset settings |
| `canvas.json` | Full canvas state: every node, edge, position, viewport, filters |
| `action_log.ndjson` | Complete log of every action taken (newline-delimited JSON) |
| `findings/index.json` | Finding metadata |
| `findings/snapshots/*.png` | Canvas snapshots attached to findings |
| `vector_manifest.json` | Library reference (names and doc list, not the actual files) |

**Use case:** Share your investigation with a colleague. They import the `.g-lab-session` file and see exactly what you saw — same nodes, same positions, same findings.

### Canvas as PNG

A screenshot of your current graph visualization. Useful for reports, presentations, or quick sharing.

### Canvas as CSV

Two CSV sections — **nodes** and **edges** — with all their properties. Useful for importing into spreadsheets or other analysis tools.

**Node columns:** ID, labels, and all property keys.
**Edge columns:** ID, type, source ID, target ID, and all property keys.

### Importing a Session

To open someone else's investigation:

1. Click **Import** in the toolbar.
2. Select a `.g-lab-session` file.
3. G-Lab validates the file format and version, then restores the full session state.

---

## 21. Presets and Configuration

Presets are bundles of settings that control how deep and wide your graph exploration and AI queries go. They let you quickly switch between investigation styles without tweaking individual parameters.

### Built-in Presets (Standard Mode)

| Preset | Hops | Nodes/Expansion | Doc Top-K | Best For |
|--------|------|-----------------|-----------|----------|
| **Quick Look** | 1 | 10 | 3 | Fast reconnaissance. Shallow, focused. |
| **Standard Investigation** | 2 | 25 | 5 | Balanced depth and breadth. The default. |
| **Deep Dive** | 3 | 50 | 10 | Thorough exploration. More data, more time. |

### Switching Presets

Click the **preset selector** in the toolbar. Your canvas is not affected — presets only change the parameters for future expansions and queries.

### What "Hops" Means

In a graph, a **hop** is one step along a relationship. If Person A → owns → Company B → registered at → Address C, then:
- 1 hop from A: Company B
- 2 hops from A: Company B and Address C
- 3 hops from A: Anything connected to Address C

More hops means more data — but the number of results grows exponentially. Two hops from a well-connected node can easily return hundreds of results. This is why presets exist: to balance thoroughness against usability.

### What "Top-K" Means (Documents)

When the Copilot searches your document library, **top-K** means how many chunks to retrieve. A top-K of 5 means the 5 most relevant text chunks from your uploaded documents will be included as context for the AI's answer.

Higher values give the AI more context but increase processing time and cost.

---

## 22. Advanced Mode

Advanced Mode exposes all the controls that presets normally hide. Toggle it in **Settings** (gear icon in the toolbar).

### What You Get

**Per-Role Model Assignment:**
The Copilot pipeline uses multiple AI models. In Advanced Mode, you can choose different models for each role:
- **Router** — The model that classifies your question.
- **Graph Retrieval** — The model that generates database queries.
- **Synthesiser** — The model that composes the final answer.

Models are provided through OpenRouter, which gives you access to models from multiple providers (OpenAI, Anthropic, Google, Meta, etc.).

**Temperature Control:**
Temperature (0.0–1.0) controls how creative/random the AI's responses are:
- **0.0** — Deterministic. Same input = same output. Best for factual queries.
- **0.5** — Balanced. Default.
- **1.0** — More creative. Best for brainstorming hypotheses.

**Guardrail Overrides:**
Within the hard limits (see [Guardrails and Limits](#23-guardrails-and-limits)), you can adjust:
- Nodes per expansion (5–100)
- Hop count (1–5)
- Document retrieval top-K (1–20)
- Reranker top-K (1–10)

**Custom Presets:**
Save your own preset configurations with a name. Load them later or share them via session export.

---

## 23. Guardrails and Limits

G-Lab enforces limits to keep the app responsive and your investigation manageable. These are checked **before** any query runs (pre-flight), so you get immediate feedback rather than waiting for a query to fail.

### Hard Limits (Cannot Be Changed)

| Limit | Value | Why |
|-------|-------|-----|
| Canvas nodes | 500 | Browser performance degrades significantly beyond this with Cytoscape. |
| Max hops | 5 | Exponential growth — 5 hops from a well-connected node could mean millions of results. |
| Nodes per expansion | 100 | Prevents a single expansion from overwhelming the canvas. |
| Cypher query timeout | 30 seconds | Protects your Neo4j instance from runaway queries. |
| Copilot timeout | 120 seconds | Prevents hanging requests to AI models. |
| Concurrent Copilot requests | 1 | The pipeline is serialized — one question at a time. |
| Document upload size | 50 MB | Per file. Prevents memory issues during parsing. |
| Documents per library | 100 | Keeps vector search fast and focused. |

### Soft Limits (Adjustable in Advanced Mode)

| Limit | Default | Range |
|-------|---------|-------|
| Nodes per expansion | 25 | 5–100 |
| Hop count | 2 | 1–5 |
| Document retrieval top-K | 5 | 1–20 |
| Reranker top-K | 3 | 1–10 |

### Canvas Warnings

- At **400 nodes** (80%): Yellow banner — *"Canvas is getting crowded. Consider filtering."*
- At **500 nodes** (100%): Red banner — *"Node limit reached. Remove nodes or start a new session."*
- If an expansion would **exceed the cap**: A detailed message shows how many slots remain.

---

## 24. Status Indicators

The toolbar shows colored dots indicating the health of connected services.

### Neo4j Status Dot

| Color | Meaning | Impact |
|-------|---------|--------|
| **Green** | Connected and healthy | All features available |
| **Yellow** | Degraded (slow responses or intermittent errors) | Features work but may be slow |
| **Red** | Disconnected | Graph features disabled. Sessions load in read-only mode. |

### Vector Store Status Dot

| Color | Meaning | Impact |
|-------|---------|--------|
| **Violet** | Ready (ChromaDB healthy + library attached) | Document search available |
| **Gray** | Unconfigured (no ChromaDB or no library attached) | Document features disabled |
| **Red** | Degraded (ChromaDB unreachable) | Document upload/search fails |

### Copilot Status (In Panel)

During a query, the Copilot panel shows the current pipeline stage with a spinner. Between queries, it shows nothing — no status dot needed because the Copilot depends on both Neo4j and (optionally) the vector store, which have their own indicators.

---

## 25. Troubleshooting

### "Neo4j status is red"

- Verify your Neo4j instance is running: `neo4j status` or check the Neo4j Browser at http://localhost:7474.
- Check your `.env` file: are `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` correct?
- The URI should use the Bolt protocol: `bolt://localhost:7687` (not `http://`).
- If Neo4j is on a remote machine, make sure the firewall allows connections on port 7687.

### "Copilot tab is disabled"

- You need an OpenRouter API key. Sign up at https://openrouter.ai, create a key, and add it to your `.env` as `OPENROUTER_API_KEY`.
- Restart the backend after changing `.env`: `docker compose restart backend`.

### "Expansion returns no results"

- Check the Database Overview to confirm data exists for the labels/types you are expanding.
- Try expanding with fewer hops or no relationship type filter.
- Check the Neo4j status dot — if it is red, queries cannot reach the database.

### "Document upload fails"

- Check the file is a PDF or DOCX and under 50 MB.
- Check the vector store status dot — if it is red, ChromaDB is unreachable.
- Check Docker: `docker compose logs chromadb` for errors.

### "Canvas is slow / laggy"

- You likely have too many nodes. Check the node counter — anything above 300 nodes will start to feel heavy.
- Use filters to hide labels you do not need to see.
- Consider resetting the session and starting a more focused investigation.

### "Session export is missing documents"

- The `.g-lab-session` export includes a `vector_manifest.json` that lists library names and document filenames, but **does not include the actual document files**. Document libraries are workspace-level resources, not per-session. This is by design — it keeps export files small and avoids duplicating large files.

---

## 26. Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | Yes | `bolt://localhost:7687` | Bolt URI of your Neo4j instance |
| `NEO4J_USER` | Yes | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | Yes | *(none)* | Neo4j password |
| `GLAB_DATA_DIR` | No | `/data` | Where SQLite DB and logs are stored (inside container) |
| `GLAB_LOG_LEVEL` | No | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| `OPENROUTER_API_KEY` | No | *(empty)* | OpenRouter API key. Copilot is disabled without this. |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `CHROMA_HOST` | No | `chromadb` | ChromaDB hostname (Docker service name) |
| `CHROMA_PORT` | No | `8000` | ChromaDB internal port |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Sentence-transformers model for document embeddings |

### Docker Compose Services

| Service | External Port | Internal Port | Purpose |
|---------|--------------|---------------|---------|
| **frontend** | 5173 | 80 | React application (Vite build served by nginx) |
| **backend** | 8000 | 8000 | FastAPI server |
| **chromadb** | 8100 | 8000 | Vector database for document search |

All ports bind to `127.0.0.1` (localhost only) — nothing is exposed to the network by default.

### Docker Volumes

| Volume | Stores |
|--------|--------|
| `glab-data` | SQLite database, NDJSON action logs, session data |
| `chroma-data` | Vector embeddings for uploaded documents |

---

## Glossary

| Term | Definition |
|------|------------|
| **Node** | An entity in the graph (a person, company, address, etc.). Represented as a circle on the canvas. |
| **Edge / Relationship** | A connection between two nodes (owns, is a director of, located at, etc.). Represented as a line. |
| **Label** | The type of a node (e.g., `Person`, `Company`). A node can have multiple labels. |
| **Property** | A key-value attribute on a node or edge (e.g., `name: "John Smith"`). |
| **Hop** | One step along a relationship in the graph. |
| **Cypher** | Neo4j's query language. G-Lab generates and sanitizes these queries for you. |
| **Expansion** | The act of fetching a node's neighbors and adding them to the canvas. |
| **Force-directed layout** | An algorithm that positions nodes using simulated physics — connected nodes attract, unconnected nodes repel. |
| **Embedding** | A numerical vector (list of numbers) that represents the meaning of a text chunk. Similar texts have similar embeddings. |
| **Vector search** | Finding text chunks whose embeddings are most similar to a query's embedding. This is how document search works. |
| **Reranker** | A second-pass model that re-scores search results for accuracy after the initial vector search. |
| **SSE (Server-Sent Events)** | A web protocol where the server pushes data to the browser in real time. Used for streaming Copilot answers. |
| **Chunking** | Splitting a document into small, overlapping segments (~512 tokens each) for vector search. |
| **Ghost elements** | AI-proposed nodes/edges shown with dashed outlines. Not committed to the canvas until you accept them. |
| **Preset** | A bundle of settings (hop count, node limits, model choices) that you can switch between quickly. |
| **Session** | A self-contained investigation workspace with its own canvas, history, and findings. |
| **Finding** | A durable note you create during an investigation. Survives session resets. |
| **Guardrail** | A limit enforced by G-Lab to keep the app responsive and protect your database. |
| **Degraded mode** | The state when Neo4j is unreachable — sessions load read-only, graph features return errors. |

---

*G-Lab is built for investigative work. Your data stays on your machine. Your findings are yours. Happy investigating.*
