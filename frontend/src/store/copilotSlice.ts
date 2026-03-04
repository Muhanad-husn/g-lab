import type { StateCreator } from "zustand";
import type {
  CopilotMessage,
  ConfidenceScore,
  EvidenceSource,
  GraphDelta,
  GraphNode,
  GraphEdge,
} from "@/lib/types";

// Minimal interface for cross-slice writes to graphSlice.
// Avoids circular import with index.ts.
interface WithGraphActions {
  addNodes: (nodes: GraphNode[]) => void;
  addEdges: (edges: GraphEdge[]) => void;
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CopilotSlice {
  messages: CopilotMessage[];
  /** In-progress text accumulated during streaming. */
  streamingContent: string;
  isStreaming: boolean;
  pendingDelta: GraphDelta | null;
  confidence: ConfidenceScore | null;
  evidence: EvidenceSource[];
  pipelineStatus: string | null;

  startStream: () => void;
  appendTextChunk: (content: string) => void;
  setEvidence: (sources: EvidenceSource[]) => void;
  setPendingDelta: (delta: GraphDelta) => void;
  setConfidence: (score: ConfidenceScore) => void;
  setStatus: (stage: string) => void;
  /** Finalise stream: flush streamingContent as an assistant message. */
  finishStream: (sessionId: string) => void;
  clearPendingDelta: () => void;
  /** Cross-slice: apply pendingDelta to graphSlice, then clear it. */
  acceptDelta: () => void;
  addMessage: (message: CopilotMessage) => void;
  loadHistory: (messages: CopilotMessage[]) => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createCopilotSlice: StateCreator<
  CopilotSlice & WithGraphActions,
  [],
  [],
  CopilotSlice
> = (set, get) => ({
  messages: [],
  streamingContent: "",
  isStreaming: false,
  pendingDelta: null,
  confidence: null,
  evidence: [],
  pipelineStatus: null,

  startStream: () =>
    set({
      isStreaming: true,
      streamingContent: "",
      confidence: null,
      evidence: [],
      pipelineStatus: "starting",
    }),

  appendTextChunk: (content) =>
    set((state) => ({ streamingContent: state.streamingContent + content })),

  setEvidence: (sources) => set({ evidence: sources }),

  setPendingDelta: (delta) => set({ pendingDelta: delta }),

  setConfidence: (score) => set({ confidence: score }),

  setStatus: (stage) => set({ pipelineStatus: stage }),

  finishStream: (sessionId) =>
    set((state) => {
      if (!state.streamingContent) {
        return { isStreaming: false, pipelineStatus: null };
      }
      const msg: CopilotMessage = {
        id: crypto.randomUUID(),
        session_id: sessionId,
        role: "assistant",
        content: state.streamingContent,
        timestamp: new Date().toISOString(),
      };
      return {
        isStreaming: false,
        streamingContent: "",
        pipelineStatus: null,
        messages: [...state.messages, msg],
      };
    }),

  clearPendingDelta: () => set({ pendingDelta: null }),

  acceptDelta: () => {
    const state = get();
    if (state.pendingDelta) {
      state.addNodes(state.pendingDelta.add_nodes);
      state.addEdges(state.pendingDelta.add_edges);
      set({ pendingDelta: null });
    }
  },

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  loadHistory: (messages) => set({ messages }),
});
