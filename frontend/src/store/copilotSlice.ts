import type { StateCreator } from "zustand";
import type {
  CopilotMessage,
  ConfidenceScore,
  EvidenceSource,
} from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CopilotSlice {
  messages: CopilotMessage[];
  /** In-progress text accumulated during streaming. */
  streamingContent: string;
  isStreaming: boolean;
  confidence: ConfidenceScore | null;
  evidence: EvidenceSource[];
  pipelineStatus: string | null;
  toolUsed:
    | { cypher: string }
    | { tool: string; params: Record<string, unknown> }
    | null;

  startStream: () => void;
  appendTextChunk: (content: string) => void;
  setEvidence: (sources: EvidenceSource[]) => void;
  appendDocEvidence: (sources: EvidenceSource[]) => void;
  setConfidence: (score: ConfidenceScore) => void;
  setStatus: (stage: string) => void;
  setToolUsed: (
    tool: { cypher: string } | { tool: string; params: Record<string, unknown> },
  ) => void;
  /** Finalise stream: flush streamingContent as an assistant message. */
  finishStream: (sessionId: string) => void;
  addMessage: (message: CopilotMessage) => void;
  loadHistory: (messages: CopilotMessage[]) => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createCopilotSlice: StateCreator<
  CopilotSlice,
  [],
  [],
  CopilotSlice
> = (set) => ({
  messages: [],
  streamingContent: "",
  isStreaming: false,
  confidence: null,
  evidence: [],
  pipelineStatus: null,
  toolUsed: null,

  startStream: () =>
    set({
      isStreaming: true,
      streamingContent: "",
      confidence: null,
      evidence: [],
      pipelineStatus: "starting",
      toolUsed: null,
    }),

  appendTextChunk: (content) =>
    set((state) => ({ streamingContent: state.streamingContent + content })),

  setEvidence: (sources) => set({ evidence: sources }),

  appendDocEvidence: (sources) =>
    set((state) => ({ evidence: [...state.evidence, ...sources] })),

  setConfidence: (score) => set({ confidence: score }),

  setStatus: (stage) => set({ pipelineStatus: stage }),

  setToolUsed: (tool) => set({ toolUsed: tool }),

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
        toolUsed: null,
        messages: [...state.messages, msg],
      };
    }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  loadHistory: (messages) => set({ messages }),
});
