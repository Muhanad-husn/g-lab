import type { StateCreator } from "zustand";
import type {
  ConversationSummary,
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
  /** True when the backend trimmed older messages from the context window. */
  contextTrimmed: boolean;

  /** Active conversation ID for the current session. */
  activeConversationId: string | null;
  /** List of conversation summaries for the current session. */
  conversations: ConversationSummary[];

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
  setContextTrimmed: (v: boolean) => void;
  /** Reset all conversation state for a fresh chat. */
  clearConversation: () => void;

  setActiveConversationId: (id: string | null) => void;
  setConversations: (conversations: ConversationSummary[]) => void;
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
  contextTrimmed: false,
  activeConversationId: null,
  conversations: [],

  startStream: () =>
    set({
      isStreaming: true,
      streamingContent: "",
      confidence: null,
      evidence: [],
      pipelineStatus: "starting",
      toolUsed: null,
      contextTrimmed: false,
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
        conversation_id: state.activeConversationId ?? "",
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

  loadHistory: (messages) =>
    set({
      messages,
      activeConversationId:
        messages.length > 0 ? messages[0].conversation_id : null,
    }),

  setContextTrimmed: (v) => set({ contextTrimmed: v }),

  clearConversation: () =>
    set({
      messages: [],
      streamingContent: "",
      confidence: null,
      evidence: [],
      toolUsed: null,
      pipelineStatus: null,
      contextTrimmed: false,
    }),

  setActiveConversationId: (id) => set({ activeConversationId: id }),

  setConversations: (conversations) => set({ conversations }),
});
