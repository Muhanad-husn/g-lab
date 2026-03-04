Close the current stage after all runs are complete.

## Phase Detection

Determine phase from stage number:
- **Stage 1–7 → Phase 1:** prefix = `ph1`, plan = `docs/IMPLEMENTATION_PLAN.md`
- **Stage 8+ → Phase 2:** prefix = `ph2`, plan = `docs/IMPLEMENTATION_PLAN_PH2.md`

## Steps

1. **Verify branch:**
   - Run `git branch --show-current` — expect `stage-N`.
   - If not on a `stage-*` branch, abort with: "Not on a stage branch."

2. **Verify all runs complete:**
   - Extract stage number N from branch name.
   - Determine phase prefix from N (see Phase Detection).
   - Run `git log --oneline --grep='<prefix>-stage-N.'` to list completed runs.
   - Compare against the run list in the implementation plan for this phase.
   - If any runs are missing, list them and abort: "Incomplete runs: N.R, N.R. Run `/next-run` to continue."

3. **Run full test suite:**
   - If stage touched backend: `cd backend && ruff check app/ && mypy app/ && pytest tests/ -x -v`
   - If stage touched frontend: `cd frontend && npx tsc --noEmit && npm test -- --run`
   - Report results. If failures, stop and let the user decide.

3a. **Commit ruff/formatter auto-fixes (if any):**
   - Run `git status` — if any files are modified, run `git diff --stat` to review.
   - If changes are purely from ruff/prettier auto-formatting (import order, unused imports, blank lines, noqa tags), stage and commit them as `<prefix>-stage-N.end: ruff/prettier auto-formatting cleanup` before proceeding.
   - If changes include substantive code edits, pause and flag them to the user.

4. **Update memory:**
   - Run `/update-docs` to sync all project memory and documentation.
   - This covers MEMORY.md, core-utils.md, and any CLAUDE.md updates.
   - See `.claude/commands/update-docs.md` for the full update protocol.

5. **Commit any final changes** (if memory or minor fixes were added).

6. **Merge to main (requires user confirmation):**
   - Inform the user: "Ready to merge `stage-N` into `main`. This requires your approval."
   - Run `git checkout main && git merge stage-N --no-ff -m "Merge stage-N: description"`
   - Note: `git push` is NOT auto-run — user pushes manually.

7. **Output:**
   - Stage completion summary
   - Test results
   - Memory updates made
   - Reminder that `git push` is manual
