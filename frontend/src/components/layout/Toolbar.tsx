import { useStore } from "@/store";
import { Button } from "@/components/ui/button";
import { PRESETS, type PresetName } from "@/lib/constants";

// ─── Neo4j status indicator ───────────────────────────────────────────────────

function StatusDot() {
  const status = useStore((s) => s.neo4jStatus);

  const color =
    status === "connected"
      ? "bg-green-500"
      : status === "degraded"
        ? "bg-yellow-500"
        : status === "disconnected"
          ? "bg-red-500"
          : "bg-muted-foreground";

  const label =
    status === "connected"
      ? "Neo4j connected"
      : status === "degraded"
        ? "Neo4j degraded"
        : status === "disconnected"
          ? "Neo4j disconnected"
          : "Neo4j status unknown";

  return (
    <span className="flex items-center gap-1.5" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="text-xs text-muted-foreground hidden sm:inline">
        {label}
      </span>
    </span>
  );
}

// ─── Preset selector ──────────────────────────────────────────────────────────

function PresetSelector() {
  const activePreset = useStore((s) => s.activePreset);
  const setPreset = useStore((s) => s.setPreset);

  return (
    <select
      value={activePreset}
      onChange={(e) => setPreset(e.target.value as PresetName)}
      className="h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
    >
      {Object.values(PRESETS).map((p) => (
        <option key={p.name} value={p.name}>
          {p.label}
        </option>
      ))}
    </select>
  );
}

// ─── Toolbar ──────────────────────────────────────────────────────────────────

export function Toolbar() {
  const session = useStore((s) => s.session);

  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-card px-3 gap-3">
      {/* Left: brand + session name */}
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-sm font-semibold text-foreground select-none">
          G-Lab
        </span>
        {session && (
          <>
            <span className="text-muted-foreground text-xs">/</span>
            <span className="truncate text-xs text-muted-foreground max-w-48">
              {session.name}
            </span>
          </>
        )}
      </div>

      {/* Right: preset selector + status */}
      <div className="flex items-center gap-3 shrink-0">
        <PresetSelector />
        <StatusDot />
        {/* New session placeholder — wired in Run 5.5 / Stage 7 */}
        <Button variant="outline" size="sm" disabled={!session}>
          New Session
        </Button>
      </div>
    </header>
  );
}
