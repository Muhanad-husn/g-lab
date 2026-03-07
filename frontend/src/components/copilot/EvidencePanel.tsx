import { useState } from "react";
import { FileSearch } from "lucide-react";
import { useStore } from "@/store";
import { ParseTierBadge } from "@/components/shared/ParseTierBadge";
import { SectionHeader } from "@/components/shared/SectionHeader";
import type { EvidenceSource } from "@/lib/types";

// ─── Evidence item ────────────────────────────────────────────────────────────

interface EvidenceItemProps {
  source: EvidenceSource;
  isHighlighted: boolean;
  onSelectGraph: (id: string) => void;
  onToggleHighlight: (id: string) => void;
}

function EvidenceItem({
  source,
  isHighlighted,
  onSelectGraph,
  onToggleHighlight,
}: EvidenceItemProps) {
  const isGraph = source.type === "graph_path";

  return (
    <div
      className={`px-3 py-2 border-b border-border last:border-b-0 ${
        isHighlighted ? "bg-muted/30" : ""
      } ${!isGraph ? "cursor-pointer hover:bg-muted/20" : ""}`}
      onClick={() => !isGraph && onToggleHighlight(source.id)}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          {isGraph ? "Graph" : "Doc"}
        </span>
        {isGraph ? (
          <button
            className="text-[10px] font-mono text-primary hover:underline truncate max-w-[140px]"
            title={`Select ${source.id} on canvas`}
            onClick={(e) => {
              e.stopPropagation();
              onSelectGraph(source.id);
            }}
          >
            {source.id}
          </button>
        ) : (
          <>
            {source.filename && (
              <span
                className="text-[10px] font-mono text-foreground truncate max-w-[110px]"
                title={source.filename}
              >
                {source.filename}
              </span>
            )}
            {source.page_number != null && (
              <span className="text-[10px] text-muted-foreground shrink-0">
                p.{source.page_number}
              </span>
            )}
            {source.parse_tier && <ParseTierBadge tier={source.parse_tier} />}
          </>
        )}
      </div>
      {source.type === "doc_chunk" && source.section_heading && (
        <p className="text-[10px] text-muted-foreground italic mb-0.5 truncate">
          {source.section_heading}
        </p>
      )}
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
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);

  if (evidence.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-muted-foreground gap-2 px-6 text-center">
        <FileSearch className="h-6 w-6 opacity-30" />
        <span className="text-xs">No evidence sources</span>
        <span className="text-[10px] opacity-60">Evidence will appear here after a Copilot query</span>
      </div>
    );
  }

  function handleToggleHighlight(id: string) {
    setHighlightedChunkId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="flex flex-col">
      <SectionHeader count={evidence.length}>Evidence</SectionHeader>
      {evidence.map((src, i) => (
        <EvidenceItem
          key={`${src.type}-${src.id}-${i}`}
          source={src}
          isHighlighted={highlightedChunkId === src.id}
          onSelectGraph={(id) => setSelectedIds([id])}
          onToggleHighlight={handleToggleHighlight}
        />
      ))}
    </div>
  );
}
