import { PanelRightClose } from "lucide-react";
import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { NodeDetail } from "./NodeDetail";
import { EdgeDetail } from "./EdgeDetail";
import { EvidencePanel } from "@/components/copilot/EvidencePanel";

// ─── Inspector ────────────────────────────────────────────────────────────────

export function Inspector() {
  const selectedIds = useStore((s) => s.selectedIds);
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const evidence = useStore((s) => s.evidence);
  const setPanelState = useStore((s) => s.setPanelState);

  const selectedId = selectedIds[0] ?? null;

  const isNode = selectedId ? nodes.some((n) => n.id === selectedId) : false;
  const isEdge = selectedId ? edges.some((e) => e.id === selectedId) : false;
  const hasEvidence = evidence.length > 0;

  const propertiesContent = (
    <ScrollArea className="flex-1">
      {!selectedId && (
        <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs gap-2">
          <span>Select a node or relationship</span>
        </div>
      )}
      {selectedId && isNode && <NodeDetail id={selectedId} />}
      {selectedId && isEdge && <EdgeDetail id={selectedId} />}
      {selectedId && !isNode && !isEdge && (
        <p className="text-xs text-muted-foreground px-3 py-2">
          Element not found in canvas
        </p>
      )}
    </ScrollArea>
  );

  return (
    <div className="flex flex-col h-full border-l border-border">
      {/* Header */}
      <div className="h-10 flex items-center px-3 border-b border-border shrink-0">
        <span className="text-xs font-semibold text-foreground">Inspector</span>
        {selectedId && (
          <span className="ml-2 text-[10px] font-mono text-muted-foreground truncate">
            {selectedId}
          </span>
        )}
        <button
          onClick={() => setPanelState("inspectorCollapsed", true)}
          title="Collapse inspector"
          className="ml-auto p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
        >
          <PanelRightClose className="h-4 w-4" />
        </button>
      </div>

      {/* Content — tabbed when evidence is available */}
      {hasEvidence ? (
        <Tabs defaultValue="properties" className="flex flex-col flex-1 overflow-hidden">
          <TabsList className="rounded-none border-b border-border bg-card w-full justify-start h-8 p-0 gap-0 shrink-0">
            <TabsTrigger
              value="properties"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 h-full text-xs"
            >
              Properties
            </TabsTrigger>
            <TabsTrigger
              value="evidence"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 h-full text-xs"
            >
              Evidence
              <span className="ml-1 text-[9px] bg-primary/20 text-primary rounded px-1">
                {evidence.length}
              </span>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="properties" className="flex-1 mt-0 overflow-hidden flex flex-col">
            {propertiesContent}
          </TabsContent>
          <TabsContent value="evidence" className="flex-1 mt-0 overflow-hidden">
            <ScrollArea className="h-full">
              <EvidencePanel />
            </ScrollArea>
          </TabsContent>
        </Tabs>
      ) : (
        propertiesContent
      )}
    </div>
  );
}
