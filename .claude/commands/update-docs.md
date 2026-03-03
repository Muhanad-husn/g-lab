Update project memory and documentation after meaningful work.

Use this command after completing a run, stage, or any session where new patterns,
gotchas, conventions, or architectural decisions were established.

## Inventory

| File | Purpose | Max size |
|------|---------|----------|
| `MEMORY.md` (auto-memory) | Stage history, gotchas, runtime patterns | 200 lines (hard — truncated after) |
| `memory/*.md` (topic files) | Detailed notes per topic; linked from MEMORY.md | Unlimited, keep focused |
| `CLAUDE.md` (root) | Project conventions, slash command registry, constraints | No limit; keep stable |
| `backend/CLAUDE.md` | Backend conventions, Neo4j/SQLite rules | No limit; keep stable |
| `frontend/CLAUDE.md` | Frontend conventions, Cytoscape/store rules | No limit; keep stable |
| `.claude/commands/core-utils.md` | Quick-ref for `app/core/` modules | Update when core modules change |

## Steps

1. **Collect changes from session:**
   - Review `git diff main --stat` (or `git log --oneline main..HEAD` if on a branch)
     to identify what changed.
   - Scan for new files in `app/core/`, `app/routers/`, `app/services/`,
     `frontend/src/`, or any new slash command in `.claude/commands/`.

2. **Determine what needs updating** — check each category:
   - **Stage history** → MEMORY.md (only after a run or stage completes)
   - **Gotchas / debugging insights** → MEMORY.md or a topic file
   - **New utility module in `app/core/`** → `core-utils.md` + backend/CLAUDE.md mention
   - **New slash command** → CLAUDE.md § Custom Slash Commands
   - **New convention or constraint** → CLAUDE.md or backend/frontend CLAUDE.md
   - **Architecture change** → `docs/ARCHITECTURE.md` (rare; confirm with user first)

3. **Apply the update rules (mandatory):**

   a. **No duplication.** MEMORY.md must NOT repeat anything in root CLAUDE.md.
      If content belongs in CLAUDE.md, put it there and remove it from MEMORY.md.

   b. **MEMORY.md ≤ 200 lines.** Before writing, count current lines:
      ```bash
      wc -l < "C:\Users\mou97\.claude\projects\D--g-lab\memory\MEMORY.md"
      ```
      If near limit, move detailed notes to a topic file under
      `C:\Users\mou97\.claude\projects\D--g-lab\memory\` (e.g., `stage-3-notes.md`)
      and link from MEMORY.md:
      `- See [stage-3-notes.md](memory/stage-3-notes.md) for details.`

   c. **Verify before writing.** Do not write speculative conclusions from reading
      a single file. Cross-check against project docs or test results.

   d. **Topic files for depth.** When a gotcha or pattern needs more than 2-3 lines
      of explanation, create a topic file (e.g., `debugging.md`, `neo4j-patterns.md`)
      and link from MEMORY.md.

   e. **core-utils.md stays current.** If any module in `app/core/` was added or
      modified, regenerate the relevant section of `core-utils.md` by reading the
      source and extracting: module path, public API (functions/classes/decorators),
      signatures, and a usage example.

   f. **Slash command registry.** If a new `.claude/commands/*.md` file was created,
      add a one-line entry to CLAUDE.md § Custom Slash Commands.

4. **Apply updates:**
   - Use the Edit tool for surgical changes. Use Write only for new files.
   - For MEMORY.md: update the appropriate section (Stage History, or add a new
     topic section). Keep entries concise — one bullet per run, sub-bullets for gotchas.
   - For CLAUDE.md files: append to the appropriate section. Do not reorganise
     existing content unless fixing an error.

5. **Output summary:**
   - List each file updated and what was changed (one line each).
   - If any file was NOT updated, explain why (e.g., "No new conventions established").
   - Flag if MEMORY.md is approaching the 200-line limit.

## What to record (cheat sheet)

| Category | Example | Where |
|----------|---------|-------|
| Run completed | `ph1-stage-2.1: Neo4j driver + health endpoint` | MEMORY.md § Stage History |
| Gotcha | `aiosqlite requires explicit commit after INSERT` | MEMORY.md § gotchas or topic file |
| Pattern | `All services use dependency injection via FastAPI Depends` | MEMORY.md or backend/CLAUDE.md |
| New core util | `app/core/monitoring.py: OperationTimer, WarningCollector` | core-utils.md |
| New command | `/check-contracts` — compares schemas | CLAUDE.md § Custom Slash Commands |
| User preference | `"always run mypy before committing"` | MEMORY.md (explicit user requests) |
| Convention | `All enum values are UPPER_SNAKE_CASE` | backend/CLAUDE.md |

## What NOT to record

- Session-specific context (current task details, temporary state)
- Anything already in CLAUDE.md (no duplication)
- Speculative or unverified conclusions
- Verbose code snippets (link to the source file instead)
