import { useState } from "react";
import { EyeOff, Eye, Trash2 } from "lucide-react";
import { useStore } from "@/store";
import { useGraphActions } from "@/hooks/useGraphActions";
import { Button } from "@/components/ui/button";

// ─── Property table ───────────────────────────────────────────────────────────

function PropertyTable({ properties }: { properties: Record<string, unknown> }) {
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

// ─── NodeDetail ───────────────────────────────────────────────────────────────

export function NodeDetail({ id }: { id: string }) {
  const node = useStore((s) => s.nodes.find((n) => n.id === id));
  const edges = useStore((s) => s.edges);
  const presetConfig = useStore((s) => s.presetConfig);
  const isCollapsed = useStore((s) => s.collapsedNodeIds.includes(id));
  const collapseNode = useStore((s) => s.collapseNode);
  const removeNode = useStore((s) => s.removeNode);
  const { expandNode } = useGraphActions();

  const [hops, setHops] = useState(presetConfig.default_hops);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [expanding, setExpanding] = useState(false);

  // Rel types from edges already connected to this node on the canvas
  const connectedTypes = [
    ...new Set(
      edges
        .filter((e) => e.source === id || e.target === id)
        .map((e) => e.type),
    ),
  ].sort();

  if (!node) {
    return (
      <p className="text-xs text-muted-foreground px-3 py-2">
        Node not found in canvas
      </p>
    );
  }

  function toggleType(type: string) {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }

  async function handleExpand() {
    setExpanding(true);
    try {
      await expandNode(id, {
        hops,
        rel_types: selectedTypes.length > 0 ? selectedTypes : null,
      });
    } finally {
      setExpanding(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      {/* Labels */}
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

      {/* Properties */}
      <div>
        <p className="px-3 text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Properties
        </p>
        <PropertyTable properties={node.properties} />
      </div>

      {/* Expand controls */}
      <div className="px-3 flex flex-col gap-2">
        {/* Hop count selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground shrink-0">Hops</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                onClick={() => setHops(n)}
                className={`h-5 w-5 rounded text-[10px] border transition-colors ${
                  hops === n
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground hover:border-primary/50"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Relationship type filter — shown only when connected edges exist */}
        {connectedTypes.length > 0 && (
          <div>
            <p className="text-[10px] text-muted-foreground mb-1">
              Filter by type (empty = all)
            </p>
            <div className="flex flex-wrap gap-1">
              {connectedTypes.map((type) => (
                <button
                  key={type}
                  onClick={() => toggleType(type)}
                  className={`px-2 py-0.5 rounded border text-[10px] transition-colors ${
                    selectedTypes.includes(type)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/50"
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
        )}

        <Button
          variant="outline"
          size="sm"
          className="w-full text-xs"
          onClick={handleExpand}
          disabled={expanding}
        >
          {expanding ? "Expanding…" : "Expand Node"}
        </Button>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs gap-1"
            onClick={() => collapseNode(id)}
          >
            {isCollapsed ? (
              <>
                <Eye className="h-3 w-3" />
                Show
              </>
            ) : (
              <>
                <EyeOff className="h-3 w-3" />
                Hide
              </>
            )}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            className="flex-1 text-xs gap-1"
            onClick={() => removeNode(id)}
          >
            <Trash2 className="h-3 w-3" />
            Remove
          </Button>
        </div>
      </div>
    </div>
  );
}
