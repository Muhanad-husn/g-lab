import { useState } from "react";
import { Settings2, EyeOff, Eye, Trash2, Route } from "lucide-react";
import { useStore } from "@/store";
import { useGraphActions } from "@/hooks/useGraphActions";
import { cytoscapeRef } from "@/lib/cytoscapeRef";
import {
  type LayoutName,
  LAYOUT_LABELS,
  runLayout,
} from "@/lib/cytoscape";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const LAYOUT_NAMES = Object.keys(LAYOUT_LABELS) as LayoutName[];

export function CanvasControls() {
  const selectedIds = useStore((s) => s.selectedIds);
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const presetConfig = useStore((s) => s.presetConfig);
  const collapsedNodeIds = useStore((s) => s.collapsedNodeIds);
  const collapseNode = useStore((s) => s.collapseNode);
  const removeNode = useStore((s) => s.removeNode);
  const { expandNode, findPaths } = useGraphActions();

  const [hops, setHops] = useState(presetConfig.default_hops);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [expanding, setExpanding] = useState(false);
  const [findingPaths, setFindingPaths] = useState(false);

  // Single selected node context
  const selectedNodeId =
    selectedIds.length === 1 &&
    nodes.some((n) => n.id === selectedIds[0])
      ? selectedIds[0]
      : null;

  // Two-node selection for path finding
  const selectedPair =
    selectedIds.length === 2 &&
    selectedIds.every((id) => nodes.some((n) => n.id === id))
      ? (selectedIds as [string, string])
      : null;

  const isCollapsed = selectedNodeId
    ? collapsedNodeIds.includes(selectedNodeId)
    : false;

  const connectedTypes = selectedNodeId
    ? [
        ...new Set(
          edges
            .filter(
              (e) => e.source === selectedNodeId || e.target === selectedNodeId,
            )
            .map((e) => e.type),
        ),
      ].sort()
    : [];

  function handleLayout(name: LayoutName) {
    if (cytoscapeRef.current) {
      runLayout(cytoscapeRef.current, name);
    }
  }

  function toggleType(type: string) {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }

  async function handleExpand() {
    if (!selectedNodeId) return;
    setExpanding(true);
    try {
      await expandNode(selectedNodeId, {
        hops,
        rel_types: selectedTypes.length > 0 ? selectedTypes : null,
      });
    } finally {
      setExpanding(false);
    }
  }

  async function handleFindPaths() {
    if (!selectedPair) return;
    setFindingPaths(true);
    try {
      await findPaths(selectedPair[0], selectedPair[1], { max_hops: hops });
    } finally {
      setFindingPaths(false);
    }
  }

  return (
    <div className="absolute top-3 right-3 z-10">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" className="h-8 w-8">
            <Settings2 className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {/* ── Layouts ── */}
          <DropdownMenuLabel className="text-xs">
            Apply Layout
          </DropdownMenuLabel>
          {LAYOUT_NAMES.map((name) => (
            <DropdownMenuItem
              key={name}
              onSelect={() => handleLayout(name)}
              className="text-xs"
            >
              {LAYOUT_LABELS[name]}
            </DropdownMenuItem>
          ))}

          {/* ── Node Actions (only when a single node is selected) ── */}
          {selectedNodeId && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs">
                Node Actions
              </DropdownMenuLabel>

              {/* Hops selector */}
              <div className="px-2 py-1.5 flex items-center gap-2">
                <span className="text-xs text-muted-foreground shrink-0">
                  Hops
                </span>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => setHops(n)}
                      className={`h-6 w-6 rounded text-[10px] border transition-colors ${
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

              {/* Relationship type filter */}
              {connectedTypes.length > 0 && (
                <div className="px-2 py-1.5">
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

              <DropdownMenuItem
                onSelect={handleExpand}
                disabled={expanding}
                className="text-xs"
              >
                {expanding ? "Expanding..." : "Expand Node"}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => collapseNode(selectedNodeId)}
                className="text-xs"
              >
                {isCollapsed ? (
                  <>
                    <Eye className="h-3 w-3 mr-2" />
                    Show
                  </>
                ) : (
                  <>
                    <EyeOff className="h-3 w-3 mr-2" />
                    Hide
                  </>
                )}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => removeNode(selectedNodeId)}
                className="text-xs text-destructive focus:text-destructive"
              >
                <Trash2 className="h-3 w-3 mr-2" />
                Remove
              </DropdownMenuItem>
            </>
          )}

          {/* ── Find Paths (when exactly two nodes are selected) ── */}
          {selectedPair && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs">
                Find Paths
              </DropdownMenuLabel>

              {/* Hops selector (reuse the same state) */}
              <div className="px-2 py-1.5 flex items-center gap-2">
                <span className="text-xs text-muted-foreground shrink-0">
                  Max hops
                </span>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => setHops(n)}
                      className={`h-6 w-6 rounded text-[10px] border transition-colors ${
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

              <DropdownMenuItem
                onSelect={handleFindPaths}
                disabled={findingPaths}
                className="text-xs"
              >
                <Route className="h-3 w-3 mr-2" />
                {findingPaths ? "Finding..." : "Shortest Path"}
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
