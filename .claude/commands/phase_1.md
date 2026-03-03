Implement Stage $ARGUMENTS of Phase 1 in one shot.

> **Prefer the run-by-run workflow instead:** `/stage-start N` → `/next-run` (repeat) → `/stage-end`.
> This command implements the entire stage at once, which is convenient for small stages but can be unwieldy for larger ones.

1. Read `docs/STRUCTURE_PH1.md` and `docs/IMPLEMENTATION_PLAN.md` — identify Stage $ARGUMENTS and all its runs.
2. Read `backend/CLAUDE.md` and/or `frontend/CLAUDE.md` for conventions relevant to this stage.
3. Use Context7 MCP to fetch current docs for any library you'll use (≤5K tokens).
4. Check `docs/ARCHITECTURE.md` §14 (Canonical Type Contracts) for schemas.
5. Implement all runs for Stage $ARGUMENTS in order, following the build order.
6. After each run, run the verify step listed in `IMPLEMENTATION_PLAN.md`.
7. Commit each run separately: `ph1-stage-$ARGUMENTS.R: description` (e.g., `ph1-stage-3.1: schemas and session/finding services`).
8. After all runs, run the full test suite for the affected layer(s).
