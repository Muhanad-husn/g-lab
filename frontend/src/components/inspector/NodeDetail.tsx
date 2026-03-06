import { useStore } from "@/store";

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
    </div>
  );
}
