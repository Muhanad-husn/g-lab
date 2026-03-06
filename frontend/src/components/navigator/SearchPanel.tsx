import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { search } from "@/api/graph";
import { useStore } from "@/store";
import { useGraphActions } from "@/hooks/useGraphActions";
import type { GraphNode } from "@/lib/types";

// ─── Result item ──────────────────────────────────────────────────────────────

interface ResultItemProps {
  node: GraphNode;
  onAdd: (node: GraphNode) => void;
  onAddExpand: (node: GraphNode) => void;
}

function ResultItem({ node, onAdd, onAddExpand }: ResultItemProps) {
  const label = node.labels[0] ?? "Node";
  // Show the first string property as display name
  const displayName =
    Object.values(node.properties).find((v) => typeof v === "string") ??
    node.id;

  return (
    <div
      className="flex items-center justify-between gap-2 px-3 py-2 hover:bg-accent/50 rounded-sm cursor-pointer"
      onClick={() => onAdd(node)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onAdd(node);
      }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <Badge variant="outline" className="shrink-0 text-xs">
          {label}
        </Badge>
        <span className="truncate text-xs text-foreground">
          {String(displayName)}
        </span>
      </div>
      <div className="flex gap-1 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={(e) => {
            e.stopPropagation();
            onAdd(node);
          }}
          title="Add to canvas"
        >
          Add
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={(e) => {
            e.stopPropagation();
            onAddExpand(node);
          }}
          title="Add to canvas and expand neighbours"
        >
          +Expand
        </Button>
      </div>
    </div>
  );
}

// ─── Search panel ─────────────────────────────────────────────────────────────

export function SearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addNodes = useStore((s) => s.addNodes);
  const storeSearchQuery = useStore((s) => s.searchQuery);
  const setSearchQuery = useStore((s) => s.setSearchQuery);
  const { expandNode } = useGraphActions();

  async function doSearch(q: string) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await search({ query: q.trim(), limit: 25 });
      setResults(data.nodes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    await doSearch(query);
  }

  // Watch for cross-component search query (e.g. from DatabaseOverview double-click)
  const prevStoreQuery = useRef("");
  useEffect(() => {
    if (storeSearchQuery && storeSearchQuery !== prevStoreQuery.current) {
      prevStoreQuery.current = storeSearchQuery;
      setQuery(storeSearchQuery);
      void doSearch(storeSearchQuery);
      setSearchQuery("");
    }
  }, [storeSearchQuery, setSearchQuery]);

  function handleAdd(node: GraphNode) {
    addNodes([node]);
  }

  function handleAddExpand(node: GraphNode) {
    addNodes([node]);
    void expandNode(node.id);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search input */}
      <form onSubmit={handleSearch} className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Search nodes…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-8 h-8 text-xs"
            disabled={loading}
          />
        </div>
      </form>

      {/* Status */}
      {error && (
        <p className="px-3 py-1 text-xs text-destructive">{error}</p>
      )}
      {!error && results.length > 0 && (
        <p className="px-3 py-1 text-xs text-muted-foreground">
          {results.length} result{results.length !== 1 ? "s" : ""}
        </p>
      )}

      {/* Results list */}
      <ScrollArea className="flex-1 px-1">
        {results.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground text-xs gap-1">
            {query ? "No results found" : "Enter a query to search"}
          </div>
        )}
        {results.map((node) => (
          <ResultItem
            key={node.id}
            node={node}
            onAdd={handleAdd}
            onAddExpand={handleAddExpand}
          />
        ))}
      </ScrollArea>
    </div>
  );
}
