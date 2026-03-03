/**
 * Dev-only overlay panel for monitoring API requests and store state.
 *
 * Conditionally rendered: `{import.meta.env.DEV && <DevPanel />}`
 * Toggle: Ctrl+Shift+D
 *
 * Tabs: [API Log] [Operations] [Store]
 * - API Log: last 50 requests with method, path, status, duration_ms
 * - Operations: currently in-flight requests with elapsed time
 * - Store: node count, edge count, session ID, neo4j status
 */
import { useCallback, useEffect, useState } from "react";

import { useStore } from "@/store";

type Tab = "api" | "operations" | "store";

function ApiLogTab() {
  const devLogs = useStore((s) => s.devLogs);
  const recent = devLogs.slice(-50).reverse();

  return (
    <div className="space-y-1 text-xs">
      {recent.length === 0 && (
        <p className="text-muted-foreground">No API requests yet.</p>
      )}
      {recent.map((log) => (
        <div
          key={log.id}
          className="flex items-center gap-2 rounded px-1 py-0.5 font-mono hover:bg-muted"
        >
          <span
            className={
              log.status >= 400 ? "text-destructive" : "text-green-600"
            }
          >
            {log.status}
          </span>
          <span className="font-semibold">{log.method}</span>
          <span className="flex-1 truncate">{log.path}</span>
          <span className="text-muted-foreground">{log.duration_ms}ms</span>
          {log.warnings.length > 0 && (
            <span className="text-yellow-600" title={log.warnings.join(", ")}>
              {log.warnings.length}w
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function OperationsTab() {
  const activeOperations = useStore((s) => s.activeOperations);
  const [, setTick] = useState(0);

  // Re-render every second to update elapsed time
  useEffect(() => {
    if (activeOperations.length === 0) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [activeOperations.length]);

  return (
    <div className="space-y-1 text-xs">
      {activeOperations.length === 0 && (
        <p className="text-muted-foreground">No operations in flight.</p>
      )}
      {activeOperations.map((op) => {
        const elapsed = Math.round((Date.now() - op.startedAt) / 1000);
        return (
          <div
            key={op.id}
            className="flex items-center gap-2 rounded px-1 py-0.5 font-mono hover:bg-muted"
          >
            <span className="animate-pulse text-blue-500">●</span>
            <span className="font-semibold">{op.type}</span>
            <span className="flex-1 truncate text-muted-foreground">
              {op.label}
            </span>
            <span>{elapsed}s</span>
          </div>
        );
      })}
    </div>
  );
}

function StoreTab() {
  const neo4jStatus = useStore((s) => s.neo4jStatus);
  const toastCount = useStore((s) => s.toasts.length);
  const opCount = useStore((s) => s.activeOperations.length);
  const logCount = useStore((s) => s.devLogs.length);

  // These selectors depend on graphSlice/sessionSlice existing.
  // Use optional chaining since they may not be wired yet.
  const nodeCount = useStore(
    (s) => ("nodes" in s ? (s.nodes as unknown[]).length : "—") as string,
  );
  const edgeCount = useStore(
    (s) => ("edges" in s ? (s.edges as unknown[]).length : "—") as string,
  );
  const sessionId = useStore((s) =>
    "session" in s && s.session
      ? String((s.session as { id?: string }).id ?? "—")
      : "—",
  );

  const statusColor: Record<string, string> = {
    connected: "text-green-600",
    degraded: "text-yellow-600",
    disconnected: "text-red-600",
    unknown: "text-muted-foreground",
  };

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">
      <span className="text-muted-foreground">Neo4j</span>
      <span className={statusColor[neo4jStatus] ?? ""}>{neo4jStatus}</span>

      <span className="text-muted-foreground">Nodes</span>
      <span>{nodeCount}</span>

      <span className="text-muted-foreground">Edges</span>
      <span>{edgeCount}</span>

      <span className="text-muted-foreground">Session</span>
      <span className="truncate">{sessionId}</span>

      <span className="text-muted-foreground">Toasts</span>
      <span>{toastCount}</span>

      <span className="text-muted-foreground">Active ops</span>
      <span>{opCount}</span>

      <span className="text-muted-foreground">Dev logs</span>
      <span>{logCount}</span>
    </div>
  );
}

const TABS: { key: Tab; label: string }[] = [
  { key: "api", label: "API Log" },
  { key: "operations", label: "Operations" },
  { key: "store", label: "Store" },
];

export function DevPanel() {
  const isOpen = useStore((s) => s.isDevPanelOpen);
  const togglePanel = useStore((s) => s.toggleDevPanel);
  const [activeTab, setActiveTab] = useState<Tab>("api");

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "D") {
        e.preventDefault();
        togglePanel();
      }
    },
    [togglePanel],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-1">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                activeTab === tab.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          onClick={togglePanel}
          className="text-xs text-muted-foreground hover:text-foreground"
          aria-label="Close dev panel"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="max-h-48 overflow-auto p-3">
        {activeTab === "api" && <ApiLogTab />}
        {activeTab === "operations" && <OperationsTab />}
        {activeTab === "store" && <StoreTab />}
      </div>
    </div>
  );
}
