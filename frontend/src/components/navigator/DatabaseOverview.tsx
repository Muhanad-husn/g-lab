import { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronRight as ChevronRightIcon, Search } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { getSchema, getSamples, getRelSamples } from "@/api/graph";
import { useStore } from "@/store";
import { getDisplayLabel } from "@/components/canvas/cytoscapeStyles";
import type { CentralNode, LabelInfo, RelTypeInfo } from "@/lib/types";

const SAMPLE_PAGE_SIZE = 5;

// ─── Count badge ──────────────────────────────────────────────────────────────

function CountBadge({ count }: { count: number | null }) {
  if (count === null) return null;
  return (
    <span className="text-[10px] text-muted-foreground tabular-nums">
      {count.toLocaleString()}
    </span>
  );
}

// ─── Sample table with pagination ─────────────────────────────────────────────

interface SampleTableProps {
  rows: Record<string, unknown>[];
  isRelType?: boolean;
  onSearchName?: (name: string) => void;
}

function SampleTable({ rows, isRelType = false, onSearchName }: SampleTableProps) {
  const [page, setPage] = useState(0);

  if (rows.length === 0) {
    return (
      <p className="px-4 py-2 text-xs text-muted-foreground">No samples found.</p>
    );
  }

  const columns = Object.keys(rows[0]);
  const totalPages = Math.ceil(rows.length / SAMPLE_PAGE_SIZE);
  const pageRows = rows.slice(
    page * SAMPLE_PAGE_SIZE,
    (page + 1) * SAMPLE_PAGE_SIZE,
  );

  return (
    <div className="overflow-x-auto px-2 pb-2">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="px-2 py-1 text-left font-medium text-muted-foreground border-b border-border"
              >
                {col}
              </th>
            ))}
            {!isRelType && onSearchName && (
              <th className="w-6 border-b border-border" />
            )}
          </tr>
        </thead>
        <tbody>
          {pageRows.map((row, i) => (
            <tr key={i} className="hover:bg-accent/30">
              {columns.map((col) => (
                <td
                  key={col}
                  className="px-2 py-1 text-foreground max-w-[120px] truncate"
                >
                  {row[col] === null ? (
                    <span className="italic text-muted-foreground">null</span>
                  ) : (
                    String(row[col])
                  )}
                </td>
              ))}
              {!isRelType && onSearchName && (
                <td className="px-1 py-1">
                  <button
                    title={`Search for ${String(row.name ?? "")}`}
                    className="p-0.5 rounded hover:bg-primary/20 text-muted-foreground hover:text-primary"
                    onClick={() => onSearchName(String(row.name ?? ""))}
                  >
                    <Search className="h-3 w-3" />
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination controls — only shown when there's more than one page */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-1 px-1">
          <span className="text-[10px] text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 0}
              className="p-0.5 rounded hover:bg-accent/50 disabled:opacity-30 disabled:cursor-not-allowed"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1}
              className="p-0.5 rounded hover:bg-accent/50 disabled:opacity-30 disabled:cursor-not-allowed"
              aria-label="Next page"
            >
              <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sample row flatteners ────────────────────────────────────────────────────

function flattenNodeRows(raw: Record<string, unknown>[]): Record<string, unknown>[] {
  return raw.map((node) => {
    const props = (node.properties ?? {}) as Record<string, unknown>;
    const name = props["_primary_value"] ?? node.id;
    const labels = Array.isArray(node.labels) ? node.labels.join(", ") : String(node.labels);
    const extra: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(props)) {
      if (!k.startsWith("_")) extra[k] = v;
    }
    return { name, labels, ...extra };
  });
}

function flattenRelRows(raw: Record<string, unknown>[]): Record<string, unknown>[] {
  return raw.map((row) => {
    const src = row.source as Record<string, unknown> | undefined;
    const rel = row.relationship as Record<string, unknown> | undefined;
    const tgt = row.target as Record<string, unknown> | undefined;
    const srcProps = (src?.properties ?? {}) as Record<string, unknown>;
    const tgtProps = (tgt?.properties ?? {}) as Record<string, unknown>;
    return {
      source: String(srcProps["_primary_value"] ?? src?.id ?? ""),
      type: String(rel?.type ?? ""),
      target: String(tgtProps["_primary_value"] ?? tgt?.id ?? ""),
    };
  });
}

// ─── Expandable label row ─────────────────────────────────────────────────────

interface LabelRowProps {
  name: string;
  count: number | null;
  isRelType?: boolean;
}

function LabelRow({ name, count, isRelType = false }: LabelRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [samples, setSamples] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(false);
  const setNavigatorTab = useStore((s) => s.setNavigatorTab);
  const setSearchQuery = useStore((s) => s.setSearchQuery);

  async function handleToggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && samples === null) {
      setLoading(true);
      try {
        const data = isRelType ? await getRelSamples(name) : await getSamples(name);
        const rows = isRelType ? flattenRelRows(data) : flattenNodeRows(data);
        setSamples(rows);
      } catch {
        setSamples([]);
      } finally {
        setLoading(false);
      }
    }
  }

  function handleSearchName(displayName: string) {
    setSearchQuery(displayName);
    setNavigatorTab("search");
  }

  return (
    <div>
      <button
        onClick={() => void handleToggle()}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs hover:bg-accent/50 rounded-sm transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRightIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 text-left text-foreground font-mono">{name}</span>
        <CountBadge count={count} />
      </button>
      {expanded && (
        <div className="ml-3 border-l border-border">
          {loading ? (
            <p className="px-4 py-2 text-xs text-muted-foreground">Loading…</p>
          ) : (
            samples !== null && (
              <SampleTable
                rows={samples}
                isRelType={isRelType}
                onSearchName={isRelType ? undefined : handleSearchName}
              />
            )
          )}
        </div>
      )}
    </div>
  );
}

// ─── Database overview ────────────────────────────────────────────────────────

function CentralNodesSection({ nodes }: { nodes: CentralNode[] }) {
  const setNavigatorTab = useStore((s) => s.setNavigatorTab);
  const setSearchQuery = useStore((s) => s.setSearchQuery);

  if (nodes.length === 0) return null;

  function handleSearch(displayName: string) {
    setSearchQuery(displayName);
    setNavigatorTab("search");
  }

  return (
    <>
      <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Central Nodes (by degree)
      </p>
      {nodes.map((n) => {
        const displayName = getDisplayLabel(n.properties, n.labels);
        return (
          <div
            key={n.id}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            <span className="flex-1 text-foreground font-mono truncate">
              {displayName}
            </span>
            <span className="text-[10px] text-muted-foreground shrink-0">
              {n.labels.join(", ")}
            </span>
            <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
              {n.degree}
            </span>
            <button
              title={`Search for ${displayName}`}
              className="p-0.5 rounded hover:bg-primary/20 text-muted-foreground hover:text-primary"
              onClick={() => handleSearch(displayName)}
            >
              <Search className="h-3 w-3" />
            </button>
          </div>
        );
      })}
      <Separator className="my-2" />
    </>
  );
}

export function DatabaseOverview() {
  const dbOverview = useStore((s) => s.dbOverview);
  const [labels, setLabels] = useState<LabelInfo[]>([]);
  const [relTypes, setRelTypes] = useState<RelTypeInfo[]>([]);
  const [centralNodes, setCentralNodes] = useState<CentralNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate from store overview if available
  useEffect(() => {
    if (dbOverview) {
      setLabels(dbOverview.schema_info.labels);
      setRelTypes(dbOverview.schema_info.relationship_types);
      setCentralNodes(dbOverview.central_nodes);
    }
  }, [dbOverview]);

  // Fallback lazy fetch if store is empty when component mounts
  useEffect(() => {
    if (dbOverview) return; // already have data from store
    let cancelled = false;
    setLoading(true);
    setError(null);

    getSchema()
      .then((schema) => {
        if (cancelled) return;
        setLabels(schema.labels);
        setRelTypes(schema.relationship_types);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Failed to load schema",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [dbOverview]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-xs">
        Loading schema…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-xs gap-1 px-4 text-center">
        <span className="text-destructive">{error}</span>
        <span className="text-[10px]">Check Neo4j connection</span>
      </div>
    );
  }

  if (labels.length === 0 && relTypes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-xs">
        Connect to Neo4j to view schema
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="px-1 py-2 space-y-0.5">
        <CentralNodesSection nodes={centralNodes} />
        {labels.length > 0 && (
          <>
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Node Labels ({labels.length})
            </p>
            {labels.map((l) => (
              <LabelRow key={l.name} name={l.name} count={l.count} />
            ))}
          </>
        )}

        {labels.length > 0 && relTypes.length > 0 && (
          <Separator className="my-2" />
        )}

        {relTypes.length > 0 && (
          <>
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Relationship Types ({relTypes.length})
            </p>
            {relTypes.map((r) => (
              <LabelRow key={r.name} name={r.name} count={r.count} isRelType />
            ))}
          </>
        )}
      </div>
    </ScrollArea>
  );
}
