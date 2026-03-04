import { useEffect, useRef, useState } from "react";
import { useStore } from "@/store";
import { useSSE } from "@/hooks/useSSE";
import { useReadOnlyMode } from "@/hooks/useReadOnlyMode";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { API_BASE } from "@/lib/constants";
import type { CopilotMessage } from "@/lib/types";

// ─── Pipeline status indicator ─────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  starting: "Starting…",
  routing: "Routing query…",
  retrieving: "Querying graph…",
  re_retrieving: "Expanding retrieval…",
  synthesising: "Synthesising answer…",
};

function StatusDot({ status }: { status: string | null }) {
  if (!status) return null;
  return (
    <div className="flex items-center gap-1.5 px-3 py-1 text-[10px] text-muted-foreground border-b border-border bg-muted/30">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
      {STATUS_LABELS[status] ?? status}
    </div>
  );
}

// ─── Message bubble ────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: CopilotMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const confidence = useStore((s) => s.confidence);
  const isAssistant = message.role === "assistant";

  return (
    <div className={`flex flex-col gap-0.5 px-3 py-2 ${isAssistant ? "" : "items-end"}`}>
      <span className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">
        {isAssistant ? "Copilot" : "You"}
      </span>
      <div
        className={`text-xs leading-relaxed whitespace-pre-wrap rounded px-2 py-1.5 max-w-[90%] ${
          isAssistant
            ? "bg-muted text-foreground self-start"
            : "bg-primary/20 text-foreground self-end"
        }`}
      >
        {message.content}
      </div>
      {/* Show confidence badge on the last assistant message only */}
      {isAssistant && confidence && (
        <div className="self-start mt-0.5">
          <ConfidenceBadge confidence={confidence} />
        </div>
      )}
    </div>
  );
}

// ─── Streaming bubble ──────────────────────────────────────────────────────────

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2">
      <span className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">
        Copilot
      </span>
      <div className="text-xs leading-relaxed whitespace-pre-wrap rounded px-2 py-1.5 bg-muted text-foreground self-start max-w-[90%]">
        {content || <span className="animate-pulse">▋</span>}
      </div>
    </div>
  );
}

// ─── Copilot panel ─────────────────────────────────────────────────────────────

export function CopilotPanel() {
  const [query, setQuery] = useState("");
  const isReadOnly = useReadOnlyMode();
  const { start: startSSE, stop: stopSSE } = useSSE();
  const scrollRef = useRef<HTMLDivElement>(null);

  const sessionId = useStore((s) => s.session?.id ?? null);
  const messages = useStore((s) => s.messages);
  const streamingContent = useStore((s) => s.streamingContent);
  const isStreaming = useStore((s) => s.isStreaming);
  const pipelineStatus = useStore((s) => s.pipelineStatus);

  // Actions are stable references in Zustand — use individual selectors to avoid
  // creating a new object every render (which would cause an infinite re-render loop).
  const startStream = useStore((s) => s.startStream);
  const appendTextChunk = useStore((s) => s.appendTextChunk);
  const setEvidence = useStore((s) => s.setEvidence);
  const setPendingDelta = useStore((s) => s.setPendingDelta);
  const setConfidence = useStore((s) => s.setConfidence);
  const setStatus = useStore((s) => s.setStatus);
  const finishStream = useStore((s) => s.finishStream);
  const addMessage = useStore((s) => s.addMessage);

  // Auto-scroll to bottom when messages or streaming content change
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, streamingContent]);

  const disabled = isStreaming || isReadOnly || !sessionId;

  async function handleSubmit() {
    const text = query.trim();
    if (!text || disabled) return;

    setQuery("");

    // Add user message to store immediately
    addMessage({
      id: crypto.randomUUID(),
      session_id: sessionId!,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    });

    startStream();

    try {
      await startSSE(
        `${API_BASE}/copilot/query`,
        { query: text, session_id: sessionId!, include_graph_context: true },
        {
          onTextChunk: ({ content }) => appendTextChunk(content),
          onEvidence: ({ sources }) => setEvidence(sources),
          onGraphDelta: (delta) => setPendingDelta(delta),
          onConfidence: (score) => setConfidence(score),
          onStatus: ({ stage }) => setStatus(stage),
          onDone: () => finishStream(sessionId!),
          onError: (err) => {
            finishStream(sessionId!);
            addMessage({
              id: crypto.randomUUID(),
              session_id: sessionId!,
              role: "assistant",
              content: `Error: ${err.message}`,
              timestamp: new Date().toISOString(),
            });
          },
        },
      );
    } catch (err) {
      finishStream(sessionId!);
      addMessage({
        id: crypto.randomUUID(),
        session_id: sessionId!,
        role: "assistant",
        content: `Connection error: ${err instanceof Error ? err.message : String(err)}`,
        timestamp: new Date().toISOString(),
      });
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <div className="flex flex-col h-full border-t border-border bg-card">
      {/* Header */}
      <div className="h-8 flex items-center px-3 border-b border-border shrink-0">
        <span className="text-xs font-semibold text-foreground">Copilot</span>
        {isReadOnly && (
          <span className="ml-2 text-[10px] text-muted-foreground">(offline)</span>
        )}
        {!sessionId && (
          <span className="ml-2 text-[10px] text-muted-foreground">(no session)</span>
        )}
        {isStreaming && (
          <button
            className="ml-auto text-[10px] text-muted-foreground hover:text-foreground"
            onClick={stopSSE}
          >
            Stop
          </button>
        )}
      </div>

      {/* Pipeline status */}
      <StatusDot status={pipelineStatus} />

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 && !isStreaming && (
          <div className="flex items-center justify-center h-20 text-xs text-muted-foreground">
            Ask Copilot a question about your graph.
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isStreaming && <StreamingBubble content={streamingContent} />}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-border p-2 flex gap-2">
        <textarea
          className="flex-1 text-xs resize-none rounded border border-input bg-background px-2 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 min-h-[40px] max-h-[80px]"
          placeholder={
            isReadOnly
              ? "Neo4j offline — Copilot unavailable"
              : !sessionId
                ? "Open a session to use Copilot"
                : "Ask about the graph… (Enter to send, Shift+Enter for newline)"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
        />
        <button
          className="shrink-0 px-3 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed self-end"
          onClick={() => void handleSubmit()}
          disabled={disabled || !query.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
