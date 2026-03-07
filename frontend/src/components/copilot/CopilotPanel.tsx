import { useCallback, useEffect, useRef, useState } from "react";
import { Bookmark, Bot, MessageSquarePlus } from "lucide-react";
import { useStore } from "@/store";
import { useSSE } from "@/hooks/useSSE";
import { useReadOnlyMode } from "@/hooks/useReadOnlyMode";
import { PanelHeader } from "@/components/shared/PanelHeader";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { API_BASE } from "@/lib/constants";
import { createFinding } from "@/api/findings";
import { clearHistory } from "@/api/copilot";
import type { CopilotMessage } from "@/lib/types";

// ─── Pipeline status indicator ─────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  starting: "Starting…",
  routing: "Routing query…",
  retrieving: "Querying graph…",
  retrieving_docs: "Retrieving documents…",
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

// ─── Cypher tool badge ──────────────────────────────────────────────────────────

function CypherBadge({ cypher }: { cypher: string }) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  return (
    <div className="px-3 py-1 border-b border-border bg-muted/40 border-l-2 border-l-primary/30">
      <button
        className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground"
        onClick={toggle}
      >
        <span className="font-mono">{">"}</span>
        <span>Cypher query used</span>
        <span className="ml-1">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <pre className="mt-1 p-1.5 rounded bg-muted text-[10px] font-mono text-foreground overflow-x-auto whitespace-pre-wrap break-all">
          {cypher}
        </pre>
      )}
    </div>
  );
}

// ─── Tool badge (structured tool selection) ─────────────────────────────────────

function ToolBadge({
  tool,
  params,
}: {
  tool: string;
  params: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  return (
    <div className="px-3 py-1 border-b border-border bg-muted/40 border-l-2 border-l-primary/30">
      <button
        className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground"
        onClick={toggle}
      >
        <span className="font-mono">{">"}</span>
        <span>
          Tool: <span className="font-semibold">{tool}</span>
        </span>
        <span className="ml-1">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <pre className="mt-1 p-1.5 rounded bg-muted text-[10px] font-mono text-foreground overflow-x-auto whitespace-pre-wrap break-all">
          {JSON.stringify(params, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── Message bubble ────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: CopilotMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const confidence = useStore((s) => s.confidence);
  const evidence = useStore((s) => s.evidence);
  const sessionId = useStore((s) => s.session?.id ?? null);
  const addFinding = useStore((s) => s.addFinding);
  const isAssistant = message.role === "assistant";
  const hasDocEvidence = evidence.some((e) => e.type === "doc_chunk");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSaveToFindings() {
    if (!sessionId || saving) return;
    setSaving(true);
    try {
      const title =
        message.content.slice(0, 80).split("\n")[0] + (message.content.length > 80 ? "…" : "");
      const finding = await createFinding(sessionId, {
        title,
        body: message.content,
      });
      addFinding(finding);
      setSaved(true);
    } catch {
      // Silently fail — user can retry
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`flex flex-col gap-1 px-3 py-2 ${isAssistant ? "" : "items-end"}`}>
      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
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
      {/* Actions row for assistant messages */}
      {isAssistant && (
        <div className="flex items-center gap-1.5 self-start mt-0.5">
          {confidence && (
            <ConfidenceBadge confidence={confidence} hasDocEvidence={hasDocEvidence} />
          )}
          {sessionId && (
            <button
              title={saved ? "Saved to findings" : "Save to findings"}
              className={`p-0.5 rounded transition-colors ${
                saved
                  ? "text-primary cursor-default"
                  : "text-muted-foreground hover:text-primary hover:bg-primary/10"
              }`}
              onClick={() => void handleSaveToFindings()}
              disabled={saving || saved}
            >
              <Bookmark className={`h-3.5 w-3.5 ${saved ? "fill-primary" : ""}`} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Streaming bubble ──────────────────────────────────────────────────────────

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-1 px-3 py-2">
      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
        Copilot
      </span>
      <div className="text-xs leading-relaxed whitespace-pre-wrap rounded px-2 py-1.5 bg-muted text-foreground self-start max-w-[90%]">
        {content || <span className="animate-pulse">▋</span>}
      </div>
    </div>
  );
}

// ─── Context warning banner ─────────────────────────────────────────────────

function ContextWarningBanner({ onNewChat }: { onNewChat: () => void }) {
  return (
    <div className="px-3 py-1.5 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-500/10 border-b border-border flex items-center gap-1.5">
      <span>
        Older messages excluded from AI context.{" "}
        <button
          className="underline hover:text-foreground"
          onClick={onNewChat}
        >
          Start a new chat
        </button>{" "}
        for best results.
      </span>
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
  const canvasSnapshot = useStore((s) => s.canvasSnapshot);
  const revertToSnapshot = useStore((s) => s.revertToSnapshot);

  // Actions are stable references in Zustand — use individual selectors to avoid
  // creating a new object every render (which would cause an infinite re-render loop).
  const startStream = useStore((s) => s.startStream);
  const appendTextChunk = useStore((s) => s.appendTextChunk);
  const setEvidence = useStore((s) => s.setEvidence);
  const appendDocEvidence = useStore((s) => s.appendDocEvidence);
  const setConfidence = useStore((s) => s.setConfidence);
  const setStatus = useStore((s) => s.setStatus);
  const setToolUsed = useStore((s) => s.setToolUsed);
  const toolUsed = useStore((s) => s.toolUsed);
  const finishStream = useStore((s) => s.finishStream);
  const addMessage = useStore((s) => s.addMessage);
  const snapshotCanvas = useStore((s) => s.snapshotCanvas);
  const contextTrimmed = useStore((s) => s.contextTrimmed);
  const setContextTrimmed = useStore((s) => s.setContextTrimmed);
  const clearConversation = useStore((s) => s.clearConversation);

  // Auto-scroll to bottom when messages or streaming content change
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, streamingContent]);

  const disabled = isStreaming || isReadOnly || !sessionId;

  async function handleNewChat() {
    if (!sessionId) return;
    try {
      await clearHistory(sessionId);
    } catch {
      // Best-effort — clear local state regardless
    }
    clearConversation();
  }

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
        {
          query: text,
          session_id: sessionId!,
          include_graph_context: true,
          model_assignments: useStore.getState().modelAssignments,
        },
        {
          onTextChunk: ({ text }) => appendTextChunk(text),
          onEvidence: ({ sources }) => setEvidence(sources),
          onDocEvidence: ({ sources }) => appendDocEvidence(sources),
          onGraphDelta: (delta) => {
            // Snapshot current canvas for undo, then replace with delta data.
            // Don't use clearGraph() because it nulls canvasSnapshot.
            snapshotCanvas();
            useStore.setState({
              nodes: delta.add_nodes,
              edges: delta.add_edges,
              positions: {},
              collapsedNodeIds: [],
            });
          },
          onConfidence: (score) => setConfidence(score),
          onToolUsed: (data) => setToolUsed(data),
          onStatus: ({ stage }) => setStatus(stage),
          onContextWarning: () => setContextTrimmed(true),
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
    <div className="flex flex-col h-full bg-card">
      {/* Header */}
      <PanelHeader title="Copilot">
        {isReadOnly && (
          <span className="text-[10px] text-muted-foreground">(offline)</span>
        )}
        {!sessionId && (
          <span className="text-[10px] text-muted-foreground">(no session)</span>
        )}
        {messages.length > 0 && !isStreaming && (
          <button
            className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1"
            onClick={() => void handleNewChat()}
            title="Start a new conversation"
          >
            <MessageSquarePlus className="h-3 w-3" />
            New Chat
          </button>
        )}
        {canvasSnapshot && !isStreaming && (
          <button
            className="text-[10px] text-muted-foreground hover:text-foreground"
            onClick={revertToSnapshot}
          >
            Undo canvas change
          </button>
        )}
        {isStreaming && (
          <button
            className="text-[10px] text-muted-foreground hover:text-foreground"
            onClick={stopSSE}
          >
            Stop
          </button>
        )}
      </PanelHeader>

      {/* Pipeline status */}
      <StatusDot status={pipelineStatus} />
      {toolUsed &&
        ("cypher" in toolUsed ? (
          <CypherBadge cypher={toolUsed.cypher} />
        ) : (
          <ToolBadge tool={toolUsed.tool} params={toolUsed.params} />
        ))}

      {/* Context window warning */}
      {contextTrimmed && !isStreaming && (
        <ContextWarningBanner onNewChat={() => void handleNewChat()} />
      )}

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground gap-2 px-6 text-center">
            <Bot className="h-6 w-6 opacity-30" />
            <span className="text-xs">Ask Copilot a question about your graph</span>
            <span className="text-[10px] opacity-60">Use natural language to explore nodes, relationships, and patterns</span>
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
