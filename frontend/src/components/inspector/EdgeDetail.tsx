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

// ─── EdgeDetail ───────────────────────────────────────────────────────────────

export function EdgeDetail({ id }: { id: string }) {
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
