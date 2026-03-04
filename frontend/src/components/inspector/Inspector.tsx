import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { NodeDetail } from "./NodeDetail";
import { EdgeDetail } from "./EdgeDetail";

// ─── Inspector ────────────────────────────────────────────────────────────────

export function Inspector() {
  const selectedIds = useStore((s) => s.selectedIds);
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);

  const selectedId = selectedIds[0] ?? null;

  const isNode = selectedId ? nodes.some((n) => n.id === selectedId) : false;
  const isEdge = selectedId ? edges.some((e) => e.id === selectedId) : false;

  return (
    <div className="flex flex-col h-full border-l border-border">
      {/* Header */}
      <div className="h-10 flex items-center px-3 border-b border-border shrink-0">
        <span className="text-xs font-semibold text-foreground">Inspector</span>
        {selectedId && (
          <span className="ml-2 text-[10px] font-mono text-muted-foreground truncate">
            {selectedId}
          </span>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {!selectedId && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs gap-2">
            <span>Select a node or relationship</span>
          </div>
        )}
        {selectedId && isNode && <NodeDetail id={selectedId} />}
        {selectedId && isEdge && <EdgeDetail id={selectedId} />}
        {selectedId && !isNode && !isEdge && (
          <p className="text-xs text-muted-foreground px-3 py-2">
            Element not found in canvas
          </p>
        )}
      </ScrollArea>
    </div>
  );
}
