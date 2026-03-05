You are helping debug G-Lab in a live running session. The user will describe issues they observe in the UI or behavior.

For each issue reported:

1. **Identify the likely source** — pinpoint the file(s) and line(s) most likely responsible based on the symptom. Use Grep/Read to verify before suggesting fixes.
2. **Check logs if relevant** — backend logs are NDJSON at `backend/logs/app.ndjson`; SQLite action_log is at `backend/glab.db`. Check these for errors matching the symptom.
3. **Read the relevant code** — always read the actual code before proposing a fix. Do not guess.
4. **Propose a minimal fix** — smallest change that addresses the root cause. No refactoring, no extra features.
5. **Apply the fix** — edit the file directly. Hooks will auto-format.
6. **Tell the user what to do** — specify if they need to restart the backend, hard-refresh the browser, or if the fix takes effect automatically (e.g., hot-reload via Vite).

## Context

- Frontend runs at http://127.0.0.1:5173 (Vite hot-reload)
- Backend runs at http://127.0.0.1:8000 (Uvicorn, must restart for Python changes)
- ChromaDB runs at http://127.0.0.1:8100
- All API endpoints are under `/api/v1`
- Backend logs: `backend/logs/app.ndjson`

## Common symptom → location mappings

| Symptom | Look here |
|---------|-----------|
| Graph not rendering / blank canvas | `frontend/src/components/GraphCanvas.tsx`, Cytoscape init |
| API call fails / 4xx | `backend/app/routers/`, check request schema vs `schemas.py` |
| Copilot panel broken | `frontend/src/components/CopilotPanel.tsx`, `store/copilotSlice.ts` |
| SSE events not arriving | `backend/app/routers/copilot.py`, `frontend/src/hooks/useSSE.ts` |
| Document upload fails | `backend/app/routers/documents.py`, `services/ingestion.py` |
| Vector search / retrieval broken | `services/documents/retrieval.py`, `services/documents/reranker.py` |
| Session not persisting | `backend/app/routers/sessions.py`, `services/session_service.py` |
| Health dot wrong color | `frontend/src/hooks/useHealthPolling.ts`, `store/monitoringSlice.ts` |
| Type errors at runtime | Check `frontend/src/lib/types.ts` vs `backend/app/models/schemas.py` |

Describe the issue and I'll diagnose and fix it.
