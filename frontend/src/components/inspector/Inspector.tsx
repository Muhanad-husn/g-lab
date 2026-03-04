import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";

// ─── Property table ───────────────────────────────────────────────────────────

function PropertyTable({
  properties,
}: {
  properties: Record<string, unknown>;
}) {
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return (
      <p className="text-xs text-muted-foreground px-3 py-2">No properties</p>
    );
  }

  return (
    <table className="w-full text-xs">
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key} className="border-b border-border last:border-0">
            <td className="px-3 py-1.5 font-medium text-muted-foreground w-1/3 align-top">
              {key}
            </td>
            <td className="px-3 py-1.5 text-foreground break-all">
              {value === null ? (
                <span className="text-muted-foreground italic">null</span>
              ) : typeof value === "boolean" ? (
                String(value)
              ) : (
                String(value)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── Node detail (inline — full component in Run 5.5) ─────────────────────────

function NodeDetail({ id }: { id: string }) {
  const node = useStore((s) => s.nodes.find((n) => n.id === id));

  if (!node) {
    return (
      <p className="text-xs text-muted-foreground px-3 py-2">
        Node not found in canvas
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <div className="px-3">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Labels
        </p>
        <div className="flex flex-wrap gap-1">
          {node.labels.map((l) => (
            <span
              key={l}
              className="inline-block rounded border border-border px-2 py-0.5 text-xs"
            >
              {l}
            </span>
          ))}
        </div>
      </div>
      <div>
        <p className="px-3 text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Properties
        </p>
        <PropertyTable properties={node.properties} />
      </div>
    </div>
  );
}

// ─── Edge detail (inline — full component in Run 5.5) ─────────────────────────

function EdgeDetail({ id }: { id: string }) {
  const edge = useStore((s) => s.edges.find((e) => e.id === id));

  if (!edge) {
    return (
      <p className="text-xs text-muted-foreground px-3 py-2">
        Relationship not found in canvas
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <div className="px-3">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Type
        </p>
        <span className="inline-block rounded border border-border px-2 py-0.5 text-xs">
          {edge.type}
        </span>
      </div>
      <div className="px-3 text-xs text-muted-foreground space-y-1">
        <p>
          <span className="font-medium text-foreground">From:</span>{" "}
          <span className="font-mono text-[10px]">{edge.source}</span>
        </p>
        <p>
          <span className="font-medium text-foreground">To:</span>{" "}
          <span className="font-mono text-[10px]">{edge.target}</span>
        </p>
      </div>
      <div>
        <p className="px-3 text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Properties
        </p>
        <PropertyTable properties={edge.properties} />
      </div>
    </div>
  );
}

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
