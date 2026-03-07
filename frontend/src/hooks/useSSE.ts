import { useCallback, useEffect, useRef } from "react";
import type {
  ConfidenceScore,
  EvidenceSource,
  GraphDelta,
} from "@/lib/types";

// ─── Handler types ────────────────────────────────────────────────────────────

export interface SSEHandlers {
  onTextChunk?: (data: { text: string }) => void;
  onEvidence?: (data: { sources: EvidenceSource[] }) => void;
  onDocEvidence?: (data: { sources: EvidenceSource[] }) => void;
  onGraphDelta?: (data: GraphDelta) => void;
  onConfidence?: (data: ConfidenceScore) => void;
  onStatus?: (data: { stage: string }) => void;
  onToolUsed?: (
    data: { cypher: string } | { tool: string; params: Record<string, unknown> },
  ) => void;
  onContextWarning?: (data: {
    messages_included: number;
    messages_total: number;
  }) => void;
  onDone?: () => void;
  onError?: (data: { code: string; message: string }) => void;
}

// ─── SSE line parser ──────────────────────────────────────────────────────────

function dispatchEvent(
  eventType: string,
  dataStr: string,
  handlers: SSEHandlers,
): void {
  if (!dataStr) return;
  let parsed: unknown;
  try {
    parsed = JSON.parse(dataStr);
  } catch {
    return;
  }

  switch (eventType) {
    case "text_chunk":
      handlers.onTextChunk?.(parsed as { text: string });
      break;
    case "evidence":
      handlers.onEvidence?.(parsed as { sources: EvidenceSource[] });
      break;
    case "doc_evidence":
      handlers.onDocEvidence?.(parsed as { sources: EvidenceSource[] });
      break;
    case "graph_delta":
      handlers.onGraphDelta?.(parsed as GraphDelta);
      break;
    case "confidence":
      handlers.onConfidence?.(parsed as ConfidenceScore);
      break;
    case "status":
      handlers.onStatus?.(parsed as { stage: string });
      break;
    case "tool_used":
      handlers.onToolUsed?.(
        parsed as
          | { cypher: string }
          | { tool: string; params: Record<string, unknown> },
      );
      break;
    case "context_warning":
      handlers.onContextWarning?.(
        parsed as { messages_included: number; messages_total: number },
      );
      break;
    case "done":
      handlers.onDone?.();
      break;
    case "error":
      handlers.onError?.(parsed as { code: string; message: string });
      break;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);

  /** Start a POST-based SSE stream. Aborts any existing stream first. */
  const start = useCallback(
    async (
      url: string,
      body: unknown,
      handlers: SSEHandlers,
    ): Promise<void> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      let response: Response;
      try {
        response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        throw err;
      }

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`SSE request failed: ${response.status} ${text}`);
      }

      if (!response.body) {
        throw new Error("SSE response has no body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              const dataStr = line.slice(5).trim();
              dispatchEvent(currentEvent, dataStr, handlers);
              currentEvent = "";
            } else if (line === "") {
              // blank line = event boundary; reset event name if not already
              currentEvent = "";
            }
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        throw err;
      } finally {
        reader.releaseLock();
      }
    },
    [],
  );

  /** Abort the current stream. */
  const stop = useCallback((): void => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // Abort on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return { start, stop };
}
