import { beforeEach, describe, expect, it } from "vitest";
import { createStore } from "zustand/vanilla";
import { createCopilotSlice, type CopilotSlice } from "@/store/copilotSlice";
import type { CopilotMessage } from "@/lib/types";

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
    expect(store.getState().confidence).toEqual({
      score: 0.85,
      band: "high",
    });
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
