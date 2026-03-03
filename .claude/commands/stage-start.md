Set up context for Stage $ARGUMENTS of Phase 1.

## Steps

1. **Git init (if needed):**
   - If `.git/` does not exist, run `git init` and create an initial commit with all existing docs and scaffold files.

2. **Branch setup:**
   - If branch `stage-$ARGUMENTS` does not exist, create and switch to it: `git checkout -b stage-$ARGUMENTS`
   - If it already exists, switch to it: `git checkout stage-$ARGUMENTS`

3. **Read context docs:**
   - `docs/STRUCTURE_PH1.md` — stage overview and build order
   - `docs/IMPLEMENTATION_PLAN.md` — detailed run breakdown for Stage $ARGUMENTS
   - `CLAUDE.md`, `backend/CLAUDE.md`, `frontend/CLAUDE.md` — conventions
   - `docs/ARCHITECTURE.md` §14 — type contracts

4. **Derive progress from git history:**
   - Run: `git log --oneline --grep='ph1-stage-$ARGUMENTS.'`
   - Parse which runs (e.g., 1.1, 1.2, …) have been committed.

5. **Output stage summary:**
   - Stage number and goal (from STRUCTURE_PH1.md)
   - List all runs with status: completed (from git) or pending
   - Identify the next run to implement
   - Hint: run `/next-run` to implement it
