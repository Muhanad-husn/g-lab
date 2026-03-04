Implement the next pending run for the current stage.

## Phase Detection

Determine phase from stage number:
- **Stage 1–7 → Phase 1:** prefix = `ph1`, plan = `docs/IMPLEMENTATION_PLAN.md`
- **Stage 8+ → Phase 2:** prefix = `ph2`, plan = `docs/IMPLEMENTATION_PLAN_PH2.md`

## Steps

1. **Get current stage from branch:**
   - Run `git branch --show-current` — expect `stage-N`.
   - If not on a `stage-*` branch, abort with: "Not on a stage branch. Run `/stage-start N` first."

2. **Get completed runs from git:**
   - Extract stage number N from branch name.
   - Determine phase prefix from N (see Phase Detection).
   - Run `git log --oneline --grep='<prefix>-stage-N.'` to list completed runs.
   - Parse run numbers from commit messages (format: `<prefix>-stage-N.R: ...`).

3. **Determine next run:**
   - Read the implementation plan for this phase to get the full list of runs for Stage N.
   - Compare against completed runs to find the next pending one.
   - If all runs are complete, inform the user: "All runs for Stage N are complete. Run `/stage-end` to close the stage."

4. **Read reference docs:**
   - `CLAUDE.md`, `backend/CLAUDE.md`, and/or `frontend/CLAUDE.md`
   - `docs/ARCHITECTURE.md` §14 for type contracts
   - Check the run's file list in the implementation plan
   - If the run touches backend services, routers, or middleware, review `/core-utils`
     for correct import paths and usage patterns.

5. **Fetch library docs:**
   - Use Context7 MCP to fetch docs for any libraries used in this run (≤5K tokens total).

6. **Implement the run:**
   - Create/modify all files listed for this run in the implementation plan.
   - Follow all conventions from CLAUDE.md files.

7. **Verify:**
   - Run the verify step listed for this run in the implementation plan.
   - If tests fail, fix and re-run (max 2 fix attempts).

8. **Commit:**
   - Stage only the files for this run: `git add [explicit file list]`
   - Commit: `git commit -m "<prefix>-stage-N.R: description"`

9. **Output:**
   - Summary of what was implemented.
   - Files created/modified.
   - Test results.
   - Next run hint (or "stage complete" if last run).
   - If this run introduced new gotchas, patterns, or core utilities, remind:
     "Run `/update-docs` to sync project memory."
