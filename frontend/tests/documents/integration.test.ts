/**
 * Frontend document library integration test.
 *
 * Simulates the full Phase 3 user flow via store actions:
 *   load libraries → attach → copilot query with doc evidence → detach
 *
 * All API calls are mocked; only Zustand store state is asserted.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createStore } from "zustand/vanilla";
import { createDocumentSlice, type DocumentSlice } from "@/store/documentSlice";
import { createCopilotSlice, type CopilotSlice } from "@/store/copilotSlice";
import type {
  DocumentLibrary,
  EvidenceSource,
  GraphNode,
  GraphEdge,
} from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeLibrary(id: string, name = "Test Library"): DocumentLibrary {
  return {
    id,
    name,
    created_at: new Date().toISOString(),
    doc_count: 2,
    chunk_count: 10,
    parse_quality: "high",
    indexed_at: new Date().toISOString(),
  };
}

function makeDocEvidenceSource(chunkId: string): EvidenceSource {
  return {
    type: "doc_chunk",
    id: chunkId,
    label: "test.pdf",
    properties: {
      text: "Corp Y owns Company X via subsidiary Z.",
      page_number: 2,
      parse_tier: "high",
    },
  };
}

// Combined store slice type used in this integration test
type TestStore = DocumentSlice &
  CopilotSlice & {
    addNodes: (nodes: GraphNode[]) => void;
    addEdges: (edges: GraphEdge[]) => void;
  };

function makeStore() {
  return createStore<TestStore>()((...a) => ({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ...createDocumentSlice(...(a as any)),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ...createCopilotSlice(...(a as any)),
    addNodes: vi.fn(),
    addEdges: vi.fn(),
  }));
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("Document Library integration flow", () => {
  let store: ReturnType<typeof makeStore>;

  beforeEach(() => {
    store = makeStore();
  });

  it("load → attach: attached library id reflects the loaded library", () => {
    const lib = makeLibrary("lib-1", "Ownership Docs");

    store.getState().loadLibraries([lib]);
    store.getState().setAttachedLibrary("lib-1");

    expect(store.getState().libraries).toHaveLength(1);
    expect(store.getState().attachedLibraryId).toBe("lib-1");
  });

  it("copilot query with doc evidence: evidence accumulates in store", () => {
    store.getState().loadLibraries([makeLibrary("lib-1")]);
    store.getState().setAttachedLibrary("lib-1");

    // Simulate SSE stream: startStream → text chunks → graph evidence → doc evidence → done
    store.getState().startStream();
    store.getState().appendTextChunk("Corp Y ");
    store.getState().appendTextChunk("owns Company X.");

    const graphEvidence: EvidenceSource = {
      type: "node",
      id: "4:abc:1",
      label: "Company X",
      properties: {},
    };
    store.getState().setEvidence([graphEvidence]);

    const docEvidence = makeDocEvidenceSource("chunk-1");
    store.getState().appendDocEvidence([docEvidence]);

    const state = store.getState();
    expect(state.streamingContent).toBe("Corp Y owns Company X.");
    expect(state.evidence).toHaveLength(2);
    expect(state.evidence[0].type).toBe("node");
    expect(state.evidence[1].type).toBe("doc_chunk");
    expect(state.evidence[1].id).toBe("chunk-1");
  });

  it("finishStream creates assistant message and clears streaming content", () => {
    store.getState().startStream();
    store.getState().appendTextChunk("Answer grounded in documents.");
    store.getState().appendDocEvidence([makeDocEvidenceSource("c1")]);

    store.getState().finishStream("sess-1");

    const state = store.getState();
    expect(state.isStreaming).toBe(false);
    expect(state.streamingContent).toBe("");
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].role).toBe("assistant");
    expect(state.messages[0].content).toBe("Answer grounded in documents.");
  });

  it("detach clears attachedLibraryId", () => {
    store.getState().loadLibraries([makeLibrary("lib-1")]);
    store.getState().setAttachedLibrary("lib-1");
    expect(store.getState().attachedLibraryId).toBe("lib-1");

    store.getState().clearAttachedLibrary();
    expect(store.getState().attachedLibraryId).toBeNull();
  });

  it("full flow: load → attach → stream with doc evidence → detach", () => {
    // Load and attach library
    store.getState().loadLibraries([makeLibrary("lib-1"), makeLibrary("lib-2")]);
    store.getState().setAttachedLibrary("lib-1");

    // Simulate a copilot response with both graph and doc evidence
    store.getState().startStream();
    store.getState().setStatus("retrieving");
    store.getState().appendTextChunk("Based on graph and documents: ");
    store.getState().appendTextChunk("Corp Y owns Company X.");
    store.getState().setEvidence([
      { type: "node", id: "4:abc:1", label: "Corp Y", properties: {} },
    ]);
    store.getState().appendDocEvidence([
      makeDocEvidenceSource("chunk-42"),
    ]);
    store.getState().setConfidence({ score: 0.88, band: "high" });
    store.getState().finishStream("sess-1");

    // Detach library after query
    store.getState().clearAttachedLibrary();

    const finalState = store.getState();
    expect(finalState.attachedLibraryId).toBeNull();
    expect(finalState.libraries).toHaveLength(2);
    expect(finalState.messages).toHaveLength(1);
    expect(finalState.evidence).toHaveLength(2);
    expect(finalState.confidence?.score).toBe(0.88);
  });

  it("removing attached library also clears attachedLibraryId", () => {
    store.getState().loadLibraries([makeLibrary("lib-1"), makeLibrary("lib-2")]);
    store.getState().setAttachedLibrary("lib-1");

    store.getState().removeLibrary("lib-1");

    expect(store.getState().attachedLibraryId).toBeNull();
    expect(store.getState().libraries).toHaveLength(1);
    expect(store.getState().libraries[0].id).toBe("lib-2");
  });

  it("multiple doc evidence append calls accumulate all sources", () => {
    store.getState().startStream();
    store.getState().appendDocEvidence([makeDocEvidenceSource("c1")]);
    store.getState().appendDocEvidence([makeDocEvidenceSource("c2")]);
    store.getState().appendDocEvidence([makeDocEvidenceSource("c3")]);

    const evidence = store.getState().evidence;
    expect(evidence).toHaveLength(3);
    expect(evidence.map((e) => e.id)).toEqual(["c1", "c2", "c3"]);
  });
});
