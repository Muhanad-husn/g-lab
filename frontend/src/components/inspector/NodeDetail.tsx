import { useStore } from "@/store";
import { SectionHeader } from "@/components/shared/SectionHeader";
import { PropertyTable } from "@/components/shared/PropertyTable";

// ─── NodeDetail ───────────────────────────────────────────────────────────────

export function NodeDetail({ id }: { id: string }) {
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
      {/* Labels */}
      <div className="px-3">
        <SectionHeader>Labels</SectionHeader>
        <div className="flex flex-wrap gap-1 px-3">
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
        <SectionHeader>Properties</SectionHeader>
        <PropertyTable properties={node.properties} />
      </div>
    </div>
  );
}
