import { useStore } from "@/store";
import type { EvidenceSource } from "@/lib/types";

// ─── Evidence item ─────────────────────────────────────────────────────────────

interface EvidenceItemProps {
  source: EvidenceSource;
  onSelect: (id: string) => void;
}

function EvidenceItem({ source, onSelect }: EvidenceItemProps) {
  const isGraph = source.type === "graph_path";

  return (
    <div className="px-3 py-2 border-b border-border last:border-b-0">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          {isGraph ? "Graph" : "Doc"}
        </span>
        {isGraph && (
          <button
            className="text-[10px] font-mono text-primary hover:underline truncate max-w-[140px]"
            title={`Select ${source.id} on canvas`}
            onClick={() => onSelect(source.id)}
          >
            {source.id}
          </button>
        )}
      </div>
      <p className="text-xs text-foreground/80 leading-relaxed line-clamp-3">
        {source.content}
      </p>
    </div>
  );
}

// ─── Evidence panel ────────────────────────────────────────────────────────────

export function EvidencePanel() {
  const evidence = useStore((s) => s.evidence);
  const setSelectedIds = useStore((s) => s.setSelectedIds);

  if (evidence.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-muted-foreground text-center">
        No evidence sources for the current answer.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="px-3 py-1.5 border-b border-border">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          Evidence ({evidence.length})
        </span>
      </div>
      {evidence.map((src, i) => (
        <EvidenceItem
          key={`${src.type}-${src.id}-${i}`}
          source={src}
          onSelect={(id) => setSelectedIds([id])}
        />
      ))}
    </div>
  );
}
