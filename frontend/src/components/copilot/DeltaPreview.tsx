import { cytoscapeRef } from "@/lib/cytoscapeRef";
import { useStore } from "@/store";
import { useGraphActions } from "@/hooks/useGraphActions";

/**
 * Overlay bar rendered inside the canvas area when Copilot has proposed a
 * graph delta. Lets the user Accept (promote ghosts to real elements) or
 * Discard (remove ghosts from canvas).
 */
export function DeltaPreview() {
  const pendingDelta = useStore((s) => s.pendingDelta);
  const clearPendingDelta = useStore((s) => s.clearPendingDelta);
  const { acceptCopilotDelta } = useGraphActions();

  if (!pendingDelta) return null;

  const nodeCount = pendingDelta.add_nodes.length;
  const edgeCount = pendingDelta.add_edges.length;

  const summary = [
    nodeCount > 0 ? `${nodeCount} node${nodeCount !== 1 ? "s" : ""}` : null,
    edgeCount > 0
      ? `${edgeCount} relationship${edgeCount !== 1 ? "s" : ""}`
      : null,
  ]
    .filter(Boolean)
    .join(" and ");

  function handleDiscard() {
    const cy = cytoscapeRef.current;
    if (cy) cy.remove(".ghost");
    clearPendingDelta();
  }

  return (
    <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-10 flex items-center gap-3 rounded-lg border border-border bg-card/95 shadow-lg backdrop-blur-sm px-4 py-2">
      <span className="text-xs text-foreground">
        Copilot suggests adding{" "}
        <span className="font-medium">{summary || "no elements"}</span>
      </span>

      <div className="flex gap-2">
        <button
          className="px-3 py-1 rounded text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90"
          onClick={acceptCopilotDelta}
        >
          Accept
        </button>
        <button
          className="px-3 py-1 rounded text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted"
          onClick={handleDiscard}
        >
          Discard
        </button>
      </div>
    </div>
  );
}
