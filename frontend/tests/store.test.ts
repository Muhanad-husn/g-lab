import { beforeEach, describe, expect, it } from "vitest";
import { createStore } from "zustand/vanilla";
import { createConfigSlice, type ConfigSlice } from "@/store/configSlice";
import { createGraphSlice, type GraphSlice } from "@/store/graphSlice";
import { createSessionSlice, type SessionSlice } from "@/store/sessionSlice";
import { createUiSlice, type UiSlice } from "@/store/uiSlice";
import { PRESETS } from "@/lib/constants";
import type { GraphNode, SessionResponse } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeNode(id: string): GraphNode {
  return { id, labels: ["Person"], properties: { name: id } };
}

function makeSession(id: string): SessionResponse {
  return {
    id,
    name: "Test Session",
    status: "active",
    canvas_state: {
      schema_version: 1,
      nodes: [],
      edges: [],
      viewport: { zoom: 1, pan: { x: 0, y: 0 } },
      filters: { hidden_labels: [], hidden_types: [] },
    },
    config: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

// ─── graphSlice ───────────────────────────────────────────────────────────────

describe("graphSlice", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<GraphSlice>>;

  beforeEach(() => {
    store = createStore<GraphSlice>()((...a: any[]) => createGraphSlice(...a));
  });

  it("addNodes deduplicates by id", () => {
    const nodeA = makeNode("a");
    const nodeB = makeNode("b");

    store.getState().addNodes([nodeA, nodeB]);
    store.getState().addNodes([nodeB, makeNode("c")]); // b is duplicate

    const nodes = store.getState().nodes;
    expect(nodes).toHaveLength(3);
    expect(nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
  });

  it("setFilters merges partial filters", () => {
    store.getState().setFilters({ hidden_labels: ["Person"] });
    expect(store.getState().filters.hidden_labels).toEqual(["Person"]);
    expect(store.getState().filters.hidden_types).toEqual([]);

    store.getState().setFilters({ hidden_types: ["KNOWS"] });
    expect(store.getState().filters.hidden_labels).toEqual(["Person"]);
    expect(store.getState().filters.hidden_types).toEqual(["KNOWS"]);
  });

  it("clearGraph resets all state", () => {
    store.getState().addNodes([makeNode("a")]);
    store.getState().setFilters({ hidden_labels: ["X"] });
    store.getState().clearGraph();

    const { nodes, edges, filters } = store.getState();
    expect(nodes).toHaveLength(0);
    expect(edges).toHaveLength(0);
    expect(filters.hidden_labels).toHaveLength(0);
  });
});

// ─── configSlice ─────────────────────────────────────────────────────────────

describe("configSlice", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<ConfigSlice>>;

  beforeEach(() => {
    store = createStore<ConfigSlice>()((...a: any[]) => createConfigSlice(...a));
  });

  it("defaults to standard preset", () => {
    expect(store.getState().activePreset).toBe("standard");
    expect(store.getState().presetConfig).toEqual(PRESETS.standard);
  });

  it("setPreset updates both activePreset and presetConfig", () => {
    store.getState().setPreset("deep_dive");
    expect(store.getState().activePreset).toBe("deep_dive");
    expect(store.getState().presetConfig).toEqual(PRESETS.deep_dive);
    expect(store.getState().presetConfig.default_hops).toBe(3);
  });

  it("setPreset to quick_look has correct expansion limit", () => {
    store.getState().setPreset("quick_look");
    expect(store.getState().presetConfig.default_expansion_limit).toBe(10);
  });
});

// ─── uiSlice (banners) ───────────────────────────────────────────────────────

describe("uiSlice — banners", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<UiSlice>>;

  beforeEach(() => {
    store = createStore<UiSlice>()((...a: any[]) => createUiSlice(...a));
  });

  it("pushBanner adds banner and returns id", () => {
    const id = store.getState().pushBanner({ level: "warning", message: "hi" });
    expect(typeof id).toBe("string");
    const banners = store.getState().banners;
    expect(banners).toHaveLength(1);
    expect(banners[0].id).toBe(id);
    expect(banners[0].level).toBe("warning");
  });

  it("dismissBanner removes by id", () => {
    const id = store.getState().pushBanner({ level: "error", message: "bad" });
    store.getState().pushBanner({ level: "warning", message: "ok" });
    expect(store.getState().banners).toHaveLength(2);

    store.getState().dismissBanner(id);
    expect(store.getState().banners).toHaveLength(1);
    expect(store.getState().banners[0].level).toBe("warning");
  });

  it("clearBanners removes all", () => {
    store.getState().pushBanner({ level: "warning", message: "a" });
    store.getState().pushBanner({ level: "error", message: "b" });
    store.getState().clearBanners();
    expect(store.getState().banners).toHaveLength(0);
  });
});

// ─── graphSlice — edge + position actions ────────────────────────────────────

describe("graphSlice — edges and positions", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<GraphSlice>>;

  beforeEach(() => {
    store = createStore<GraphSlice>()((...a: any[]) => createGraphSlice(...a));
  });

  it("addEdges deduplicates by id", () => {
    const edge = { id: "e1", type: "KNOWS", source: "a", target: "b", properties: {} };
    store.getState().addEdges([edge]);
    store.getState().addEdges([edge, { id: "e2", type: "OWNS", source: "b", target: "c", properties: {} }]);

    const edges = store.getState().edges;
    expect(edges).toHaveLength(2);
    expect(edges.map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("removeNode also removes connected edges", () => {
    store.getState().addNodes([makeNode("a"), makeNode("b")]);
    store.getState().addEdges([
      { id: "e1", type: "KNOWS", source: "a", target: "b", properties: {} },
      { id: "e2", type: "OWNS", source: "b", target: "a", properties: {} },
    ]);
    store.getState().removeNode("a");

    expect(store.getState().nodes).toHaveLength(1);
    expect(store.getState().edges).toHaveLength(0);
  });

  it("setPositions merges without replacing existing entries", () => {
    store.getState().setPositions({ a: { x: 10, y: 20 } });
    store.getState().setPositions({ b: { x: 30, y: 40 } });

    const pos = store.getState().positions;
    expect(pos["a"]).toEqual({ x: 10, y: 20 });
    expect(pos["b"]).toEqual({ x: 30, y: 40 });
  });

  it("setPositions overwrites existing position for the same id", () => {
    store.getState().setPositions({ a: { x: 10, y: 20 } });
    store.getState().setPositions({ a: { x: 99, y: 99 } });

    expect(store.getState().positions["a"]).toEqual({ x: 99, y: 99 });
  });
});

// ─── uiSlice — selection ──────────────────────────────────────────────────────

describe("uiSlice — selection", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<UiSlice>>;

  beforeEach(() => {
    store = createStore<UiSlice>()((...a: any[]) => createUiSlice(...a));
  });

  it("setSelectedIds updates the selection", () => {
    store.getState().setSelectedIds(["n1", "n2"]);
    expect(store.getState().selectedIds).toEqual(["n1", "n2"]);
  });

  it("clearSelection empties selectedIds", () => {
    store.getState().setSelectedIds(["n1"]);
    store.getState().clearSelection();
    expect(store.getState().selectedIds).toHaveLength(0);
  });

  it("setSelectedIds replaces previous selection", () => {
    store.getState().setSelectedIds(["n1"]);
    store.getState().setSelectedIds(["n2", "n3"]);
    expect(store.getState().selectedIds).toEqual(["n2", "n3"]);
  });
});

// ─── sessionSlice ─────────────────────────────────────────────────────────────

describe("sessionSlice", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<SessionSlice>>;

  beforeEach(() => {
    store = createStore<SessionSlice>()(
      (...a: any[]) => createSessionSlice(...a),
    );
  });

  it("setSession stores the session", () => {
    const session = makeSession("sess-1");
    store.getState().setSession(session);
    expect(store.getState().session?.id).toBe("sess-1");
  });

  it("clearSession resets session and findings", () => {
    store.getState().setSession(makeSession("sess-1"));
    store.getState().addFinding({
      id: "f1",
      session_id: "sess-1",
      title: "Note",
      body: "content",
      has_snapshot: false,
      canvas_context: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    store.getState().clearSession();
    expect(store.getState().session).toBeNull();
    expect(store.getState().findings).toHaveLength(0);
  });

  it("setSession(null) clears session without touching findings", () => {
    store.getState().setSession(null);
    expect(store.getState().session).toBeNull();
  });
});
