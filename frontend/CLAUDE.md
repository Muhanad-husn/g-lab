# Frontend Conventions

## General

- **Zustand** for state management, slices in `src/store/`
- **Tailwind CSS only** — no inline styles, no CSS modules, no styled-components
- **shadcn/ui** for all non-canvas UI (panels, dialogs, forms, toasts)
- **Cytoscape.js** for graph rendering — managed via `useRef`, not the React wrapper's state
- API calls in `src/api/` — always unwrap the envelope in `client.ts`
- Types in `src/lib/types.ts` — must match backend Pydantic schemas (see ARCHITECTURE.md §14)

## Cytoscape Rules

These are the most common sources of bugs. Follow exactly.

- **Instance management:** Create via `cytoscape({ container: ref.current })` in a `useEffect`. Store in `useRef`. Destroy on unmount.
- **Always batch operations:** Wrap multi-element adds/removes in `cy.startBatch()` / `cy.endBatch()`. Without this, adding 25 nodes triggers 25 layout recalculations.
- **Run layout after batch add**, not after each individual add.
- **Position writeback:** Debounce `cy.on('position')` callbacks at 200ms before writing to Zustand. The brief inconsistency window after user drag is fine — don't try to make it synchronous.
- **Source of truth split:** Zustand `graphSlice` owns node/edge identity and properties. Cytoscape owns positions and viewport.
- **Inbound sync (store → Cytoscape):** When `graphSlice.nodes` or `graphSlice.edges` change, diff current Cytoscape elements against the store. Apply `cy.add()` / `cy.remove()` for the delta, batched.
- **Outbound sync (Cytoscape → store):** Position changes (layout completion or user drag) are debounced and written to `graphSlice.positions`.
- **Selection:** `cy.on('tap')` updates `uiSlice.selectedIds`. The Inspector subscribes to this.
- **Ghost elements (Phase 2):** AI-proposed nodes/edges use `cy.add(elements).addClass('ghost')` — dashed borders, reduced opacity, non-interactive until committed.

## Store Rules

- **Slices:** `graphSlice`, `sessionSlice`, `uiSlice`, `configSlice` (Phase 1), `copilotSlice` (Phase 2)
- Slices may **read** each other (e.g., `copilotSlice` reads `graphSlice.nodes` for context).
- Writes **target a single slice** — one exception: "accept graph delta" clears `copilotSlice.pendingDelta` and applies to `graphSlice` in a single action.
- Use `StateCreator` type for slice definitions. See Zustand "slices pattern" recipe.

## API Rules

- Thin `fetch` wrapper in `src/api/client.ts` — prepends base URL, unwraps `{ data, warnings, meta }` envelope, throws typed errors.
- No Axios. Native `fetch` is sufficient.
- SSE consumption (Phase 2): native `EventSource` API with thin wrapper for retry + structured message parsing.

## Component → Store → API Dependency Map

Use this to understand what each component needs and what can be built in parallel.

```
Component                Store reads              Store writes           API calls
─────────────────────────────────────────────────────────────────────────────────────
Toolbar                  sessionSlice.name        —                      —
                         configSlice.preset
                         (neo4j status)

MainLayout               uiSlice.panelStates      —                      —

SearchPanel              —                        graphSlice.addNodes    graph.search()
                                                  uiSlice.select

FilterPanel              graphSlice.nodes         graphSlice.setFilters  —
                         graphSlice.filters

FindingsPanel            sessionSlice.findings    sessionSlice.addFinding findings.create()
                                                                        findings.list()

DatabaseOverview         —                        —                      graph.schema()
                                                                        graph.samples()

CytoscapeCanvas          graphSlice.nodes         graphSlice.positions   —
                         graphSlice.edges         uiSlice.selectedIds
                         graphSlice.filters

CanvasBanners            graphSlice.nodes.length  —                      —

Inspector                uiSlice.selectedIds      —                      —
                         graphSlice.nodes
                         graphSlice.edges

NodeDetail               (props from Inspector)   —                      —
EdgeDetail               (props from Inspector)   —                      —
```

## Testing

```bash
npm test -- --run          # vitest unit tests
npx tsc --noEmit           # type check
```

## Lint

```bash
npx eslint src/ --fix && npx prettier --write src/
```
