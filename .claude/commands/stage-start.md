Set up context for Stage $ARGUMENTS.

## Phase Detection

Determine phase from stage number:
- **Stage 1–7 → Phase 1:** prefix = `ph1`, plan = `docs/IMPLEMENTATION_PLAN.md`, structure = `docs/STRUCTURE_PH1.md`
- **Stage 8+ → Phase 2:** prefix = `ph2`, plan = `docs/IMPLEMENTATION_PLAN_PH2.md`, structure = `docs/STRUCTURE_PH2.md` (if exists, else use plan file only)

## Steps

1. **Git init (if needed):**
   - If `.git/` does not exist, run `git init` and create an initial commit with all existing docs and scaffold files.

2. **Branch setup:**
   - If branch `stage-$ARGUMENTS` does not exist, create and switch to it: `git checkout -b stage-$ARGUMENTS`
   - If it already exists, switch to it: `git checkout stage-$ARGUMENTS`

3. **Read context docs:**
   - The structure doc for this phase (see Phase Detection above)
   - The implementation plan for this phase — detailed run breakdown for Stage $ARGUMENTS
   - `CLAUDE.md`, `backend/CLAUDE.md`, `frontend/CLAUDE.md` — conventions
   - `docs/ARCHITECTURE.md` §14 — type contracts

4. **Derive progress from git history:**
   - Run: `git log --oneline --grep='<prefix>-stage-$ARGUMENTS.'` (using the phase prefix)
   - Parse which runs (e.g., 8.1, 8.2, …) have been committed.

5. **Output stage summary:**
   - Stage number, phase, and goal
   - List all runs with status: completed (from git) or pending
   - Identify the next run to implement
   - Hint: run `/next-run` to implement it
