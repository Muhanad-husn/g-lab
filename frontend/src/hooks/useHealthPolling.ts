/**
 * Polls `GET /health` every 30s and updates `monitoringSlice.neo4jStatus`.
 *
 * On status transitions: fires a toast notification. When Neo4j is
 * degraded/disconnected, graph-dependent UI should be disabled (components
 * read `neo4jStatus` from the store).
 *
 * Mount once in `App.tsx`:
 * ```tsx
 * function App() {
 *   useHealthPolling();
 *   return <MainLayout />;
 * }
 * ```
 */
import { useCallback, useEffect, useRef } from "react";

import { useStore } from "@/store";
import type { CopilotStatus, Neo4jConnectionStatus } from "@/store/monitoringSlice";

const POLL_INTERVAL_MS = 30_000;

interface HealthResponse {
  data: {
    status: string;
    neo4j: Neo4jConnectionStatus;
    copilot?: CopilotStatus;
  };
}

export function useHealthPolling(): void {
  const setNeo4jStatus = useStore((s) => s.setNeo4jStatus);
  const setCopilotStatus = useStore((s) => s.setCopilotStatus);
  const addToast = useStore((s) => s.addToast);
  const prevStatusRef = useRef<Neo4jConnectionStatus>("unknown");

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/health");
      if (!res.ok) {
        handleTransition("degraded");
        return;
      }
      const body: HealthResponse = await res.json();
      handleTransition(body.data.neo4j ?? "unknown");
      setCopilotStatus(body.data.copilot ?? "unknown");
    } catch {
      handleTransition("disconnected");
    }
  }, [setCopilotStatus]);

  function handleTransition(next: Neo4jConnectionStatus): void {
    const prev = prevStatusRef.current;
    setNeo4jStatus(next);
    prevStatusRef.current = next;

    if (prev === next || prev === "unknown") return;

    if (next === "connected" && prev !== "connected") {
      addToast({
        level: "success",
        title: "Neo4j connected",
        duration: 3000,
      });
    } else if (next === "degraded") {
      addToast({
        level: "warning",
        title: "Neo4j connection degraded",
        message: "Some graph operations may be unavailable.",
        duration: 0,
      });
    } else if (next === "disconnected") {
      addToast({
        level: "error",
        title: "Neo4j disconnected",
        message: "Graph operations are unavailable.",
        duration: 0,
      });
    }
  }

  useEffect(() => {
    // Initial poll on mount
    poll();

    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [poll]);
}
