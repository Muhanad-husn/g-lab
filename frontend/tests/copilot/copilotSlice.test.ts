import { beforeEach, describe, expect, it } from "vitest";
import { createStore } from "zustand/vanilla";
import { createCopilotSlice, type CopilotSlice } from "@/store/copilotSlice";
import { createGraphSlice, type GraphSlice } from "@/store/graphSlice";
import type { CopilotMessage, GraphDelta } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeDelta(nodeCount = 2, edgeCount = 1): GraphDelta {
  return {
    add_nodes: Array.from({ length: nodeCount }, (_, i) => ({
      id: `ghost-node-${i}`,
      labels: ["Person"],
      properties: { name: `Ghost ${i}` },
    })),
    add_edges: Array.from({ length: edgeCount }, (_, i) => ({
      id: `ghost-edge-${i}`,
      type: "KNOWS",
      source: "ghost-node-0",
      target: "ghost-node-1",
      properties: {},
    })),
  };
}

// ─── copilotSlice — standalone ────────────────────────────────────────────────

describe("copilotSlice — initial state", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<CopilotSlice>>;

  beforeEach(() => {
    store = createStore<CopilotSlice>()((...a: any[]) =>
      createCopilotSlice(...a),
    );
  });

  it("has empty initial state", () => {
    const s = store.getState();
    expect(s.messages).toHaveLength(0);
    expect(s.streamingContent).toBe("");
    expect(s.isStreaming).toBe(false);
    expect(s.pendingDelta).toBeNull();
    expect(s.confidence).toBeNull();
    expect(s.evidence).toHaveLength(0);
    expect(s.pipelineStatus).toBeNull();
  });
});

describe("copilotSlice — stream lifecycle", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<CopilotSlice>>;

  beforeEach(() => {
    store = createStore<CopilotSlice>()((...a: any[]) =>
      createCopilotSlice(...a),
    );
  });

  it("startStream sets isStreaming and resets fields", () => {
    store.getState().startStream();
    const s = store.getState();
    expect(s.isStreaming).toBe(true);
    expect(s.streamingContent).toBe("");
    expect(s.pipelineStatus).toBe("starting");
    expect(s.confidence).toBeNull();
    expect(s.evidence).toHaveLength(0);
  });

  it("appendTextChunk accumulates content", () => {
    store.getState().startStream();
    store.getState().appendTextChunk("Hello ");
    store.getState().appendTextChunk("world");
    expect(store.getState().streamingContent).toBe("Hello world");
  });

  it("setStatus updates pipelineStatus", () => {
    store.getState().setStatus("retrieving");
    expect(store.getState().pipelineStatus).toBe("retrieving");
  });

  it("setEvidence stores sources", () => {
    const sources = [
      { type: "graph_path" as const, id: "n1", content: "Alice" },
    ];
    store.getState().setEvidence(sources);
    expect(store.getState().evidence).toEqual(sources);
  });

  it("setConfidence stores score", () => {
    store.getState().setConfidence({ score: 0.85, band: "high" });
    expect(store.getState().confidence).toEqual({ score: 0.85, band: "high" });
  });

  it("setPendingDelta stores delta", () => {
    const delta = makeDelta();
    store.getState().setPendingDelta(delta);
    expect(store.getState().pendingDelta).toEqual(delta);
  });

  it("clearPendingDelta nulls delta", () => {
    store.getState().setPendingDelta(makeDelta());
    store.getState().clearPendingDelta();
    expect(store.getState().pendingDelta).toBeNull();
  });

  it("finishStream flushes streamingContent as assistant message", () => {
    store.getState().startStream();
    store.getState().appendTextChunk("The answer is 42.");
    store.getState().finishStream("sess-123");

    const s = store.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingContent).toBe("");
    expect(s.pipelineStatus).toBeNull();
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0].role).toBe("assistant");
    expect(s.messages[0].content).toBe("The answer is 42.");
    expect(s.messages[0].session_id).toBe("sess-123");
  });

  it("finishStream with empty content does not append a message", () => {
    store.getState().startStream();
    store.getState().finishStream("sess-123");
    expect(store.getState().messages).toHaveLength(0);
    expect(store.getState().isStreaming).toBe(false);
  });

  it("addMessage appends a message directly", () => {
    const msg: CopilotMessage = {
      id: "m1",
      session_id: "sess-1",
      role: "user",
      content: "Hello?",
      timestamp: new Date().toISOString(),
    };
    store.getState().addMessage(msg);
    expect(store.getState().messages).toHaveLength(1);
    expect(store.getState().messages[0].id).toBe("m1");
  });

  it("loadHistory replaces messages", () => {
    store.getState().addMessage({
      id: "old",
      session_id: "s",
      role: "user",
      content: "old",
      timestamp: new Date().toISOString(),
    });

    const history: CopilotMessage[] = [
      {
        id: "h1",
        session_id: "s",
        role: "user",
        content: "Hi",
        timestamp: new Date().toISOString(),
      },
      {
        id: "h2",
        session_id: "s",
        role: "assistant",
        content: "Hello!",
        timestamp: new Date().toISOString(),
      },
    ];
    store.getState().loadHistory(history);
    const messages = store.getState().messages;
    expect(messages).toHaveLength(2);
    expect(messages[0].id).toBe("h1");
    expect(messages[1].id).toBe("h2");
  });
});

// ─── copilotSlice — acceptDelta cross-slice ───────────────────────────────────

type CombinedStore = CopilotSlice & GraphSlice;

describe("copilotSlice — acceptDelta (cross-slice)", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<CombinedStore>>;

  beforeEach(() => {
    store = createStore<CombinedStore>()((...a: any[]) => ({
      ...createGraphSlice(...a),
      ...createCopilotSlice(...a),
    }));
  });

  it("acceptDelta adds nodes and edges to graphSlice", () => {
    const delta = makeDelta(2, 1);
    store.getState().setPendingDelta(delta);
    store.getState().acceptDelta();

    const { nodes, edges } = store.getState();
    expect(nodes).toHaveLength(2);
    expect(edges).toHaveLength(1);
    expect(nodes.map((n) => n.id)).toEqual(["ghost-node-0", "ghost-node-1"]);
  });

  it("acceptDelta clears pendingDelta after applying", () => {
    store.getState().setPendingDelta(makeDelta());
    store.getState().acceptDelta();
    expect(store.getState().pendingDelta).toBeNull();
  });

  it("acceptDelta is a no-op when pendingDelta is null", () => {
    store.getState().acceptDelta();
    expect(store.getState().nodes).toHaveLength(0);
    expect(store.getState().edges).toHaveLength(0);
  });

  it("acceptDelta deduplicates with existing graph nodes", () => {
    const node = {
      id: "existing",
      labels: ["Person"],
      properties: {},
    };
    store.getState().addNodes([node]);

    const delta: GraphDelta = {
      add_nodes: [node, { id: "new-node", labels: ["Org"], properties: {} }],
      add_edges: [],
    };
    store.getState().setPendingDelta(delta);
    store.getState().acceptDelta();

    // existing node not duplicated
    expect(store.getState().nodes).toHaveLength(2);
    expect(store.getState().nodes.map((n) => n.id)).toContain("existing");
    expect(store.getState().nodes.map((n) => n.id)).toContain("new-node");
  });
});
