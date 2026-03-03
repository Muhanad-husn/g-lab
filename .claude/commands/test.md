Determine which part of the codebase was most recently modified.
- If backend: run `cd backend && ruff check app/ && pytest tests/unit/ -x -v`
- If frontend: run `cd frontend && npx tsc --noEmit && npm test -- --run`
- Report results concisely.