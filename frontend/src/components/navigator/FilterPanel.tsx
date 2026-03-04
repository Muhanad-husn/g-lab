import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

// ─── Toggle row ───────────────────────────────────────────────────────────────

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
      <span className={hidden ? "text-muted-foreground line-through" : "text-foreground"}>
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

// ─── Filter panel ─────────────────────────────────────────────────────────────

export function FilterPanel() {
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const filters = useStore((s) => s.filters);
  const setFilters = useStore((s) => s.setFilters);

  // Derive unique labels and types from current canvas content
  const labels = [...new Set(nodes.flatMap((n) => n.labels))].sort();
  const types = [...new Set(edges.map((e) => e.type))].sort();

  function toggleLabel(label: string) {
    const hidden = filters.hidden_labels.includes(label)
      ? filters.hidden_labels.filter((l) => l !== label)
      : [...filters.hidden_labels, label];
    setFilters({ hidden_labels: hidden });
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
              <ToggleRow
                key={label}
                label={label}
                hidden={filters.hidden_labels.includes(label)}
                onToggle={() => toggleLabel(label)}
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
