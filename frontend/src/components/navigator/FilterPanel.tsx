import { Layers } from "lucide-react";
import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

// ─── Toggle row (for edge types — unchanged two-state) ──────────────────────

interface ToggleRowProps {
  label: string;
  hidden: boolean;
  onToggle: () => void;
}

function ToggleRow({ label, hidden, onToggle }: ToggleRowProps) {
  return (
    <button
      onClick={onToggle}
      className="flex w-full items-center justify-between px-3 py-1.5 text-xs hover:bg-accent/50 rounded-sm transition-colors"
    >
      <span
        className={
          hidden
            ? "text-muted-foreground line-through"
            : "text-foreground"
        }
      >
        {label}
      </span>
      <span
        className={`h-4 w-4 rounded border text-[10px] flex items-center justify-center ${
          hidden
            ? "border-muted-foreground text-muted-foreground"
            : "border-primary bg-primary text-primary-foreground"
        }`}
      >
        {hidden ? "" : "✓"}
      </span>
    </button>
  );
}

// ─── Label row (three-state: visible → collapsed → hidden) ──────────────────

type LabelState = "visible" | "collapsed" | "hidden";

interface LabelRowProps {
  label: string;
  count: number;
  state: LabelState;
  onCycle: () => void;
}

function LabelRow({ label, count, state, onCycle }: LabelRowProps) {
  return (
    <button
      onClick={onCycle}
      className="flex w-full items-center justify-between px-3 py-1.5 text-xs hover:bg-accent/50 rounded-sm transition-colors"
    >
      <span
        className={
          state === "hidden"
            ? "text-muted-foreground line-through"
            : state === "collapsed"
              ? "text-muted-foreground italic"
              : "text-foreground"
        }
      >
        {label} ({count})
      </span>
      <span
        className={`h-4 w-4 rounded border text-[10px] flex items-center justify-center ${
          state === "visible"
            ? "border-primary bg-primary text-primary-foreground"
            : state === "collapsed"
              ? "border-amber-500 text-amber-500"
              : "border-muted-foreground text-muted-foreground"
        }`}
      >
        {state === "visible" ? (
          "✓"
        ) : state === "collapsed" ? (
          <Layers className="h-2.5 w-2.5" />
        ) : (
          "—"
        )}
      </span>
    </button>
  );
}

// ─── Filter panel ─────────────────────────────────────────────────────────────

export function FilterPanel() {
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);

  // Derive unique labels and types from current canvas content
  const labels = [...new Set(nodes.flatMap((n) => n.labels))].sort();
  const types = [...new Set(edges.map((e) => e.type))].sort();

  // Count nodes per label
  const labelCounts = new Map<string, number>();
  for (const node of nodes) {
    for (const label of node.labels) {
      labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);
    }
  }

  function getLabelState(label: string): LabelState {
    if (filters.collapsed_labels.includes(label)) return "collapsed";
    if (filters.hidden_labels.includes(label)) return "hidden";
    return "visible";
  }

  function cycleLabelState(label: string) {
    const state = getLabelState(label);
    if (state === "visible") {
      // visible → collapsed
      setFilters({
        collapsed_labels: [...filters.collapsed_labels, label],
      });
    } else if (state === "collapsed") {
      // collapsed → hidden
      setFilters({
        collapsed_labels: filters.collapsed_labels.filter(
          (l) => l !== label,
        ),
        hidden_labels: [...filters.hidden_labels, label],
      });
    } else {
      // hidden → visible
      setFilters({
        hidden_labels: filters.hidden_labels.filter((l) => l !== label),
      });
    }
  }

  function toggleType(type: string) {
    const hidden = filters.hidden_types.includes(type)
      ? filters.hidden_types.filter((t) => t !== type)
      : [...filters.hidden_types, type];
    setFilters({ hidden_types: hidden });
  }

  if (labels.length === 0 && types.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-xs gap-2 px-3">
        <span>Add nodes to canvas to filter</span>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="px-1 py-2 space-y-1">
        {labels.length > 0 && (
          <>
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Node Labels
            </p>
            {labels.map((label) => (
              <LabelRow
                key={label}
                label={label}
                count={labelCounts.get(label) ?? 0}
                state={getLabelState(label)}
                onCycle={() => cycleLabelState(label)}
              />
            ))}
          </>
        )}

        {labels.length > 0 && types.length > 0 && (
          <Separator className="my-2" />
        )}

        {types.length > 0 && (
          <>
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Relationship Types
            </p>
            {types.map((type) => (
              <ToggleRow
                key={type}
                label={type}
                hidden={filters.hidden_types.includes(type)}
                onToggle={() => toggleType(type)}
              />
            ))}
          </>
        )}
      </div>
    </ScrollArea>
  );
}
