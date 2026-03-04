import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SearchPanel } from "./SearchPanel";
import { FilterPanel } from "./FilterPanel";
import { FindingsPanel } from "./FindingsPanel";
import { DatabaseOverview } from "./DatabaseOverview";
import { useStore } from "@/store";
import type { CopilotMessage } from "@/lib/types";

// ─── Copilot history (read-only transcript) ───────────────────────────────────

function CopilotHistory() {
  const messages = useStore((s) => s.messages);

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-20 text-xs text-muted-foreground px-3 text-center">
        No conversation yet. Ask Copilot a question from the bottom panel.
      </div>
    );
  }

  return (
    <div className="flex flex-col divide-y divide-border">
      {messages.map((msg: CopilotMessage) => (
        <div key={msg.id} className={`px-3 py-2 ${msg.role === "user" ? "bg-muted/30" : ""}`}>
          <div className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            {msg.role === "user" ? "You" : "Copilot"}
          </div>
          <p className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">
            {msg.content}
          </p>
        </div>
      ))}
    </div>
  );
}

// ─── Navigator ────────────────────────────────────────────────────────────────

export function Navigator() {
  return (
    <Tabs defaultValue="search" className="flex flex-col h-full">
      <TabsList className="rounded-none border-b border-border bg-card w-full justify-start h-10 p-0 gap-0">
        <TabsTrigger
          value="search"
          className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 h-full text-xs"
        >
          Search
        </TabsTrigger>
        <TabsTrigger
          value="filters"
          className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 h-full text-xs"
        >
          Filters
        </TabsTrigger>
        <TabsTrigger
          value="findings"
          className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 h-full text-xs"
        >
          Findings
        </TabsTrigger>
        <TabsTrigger
          value="database"
          className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 h-full text-xs"
        >
          Database
        </TabsTrigger>
        <TabsTrigger
          value="copilot"
          className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 h-full text-xs"
        >
          Copilot
        </TabsTrigger>
      </TabsList>

      <TabsContent value="search" className="flex-1 mt-0 overflow-hidden">
        <SearchPanel />
      </TabsContent>

      <TabsContent value="filters" className="flex-1 mt-0 overflow-hidden">
        <FilterPanel />
      </TabsContent>

      <TabsContent value="findings" className="flex-1 mt-0 overflow-hidden">
        <FindingsPanel />
      </TabsContent>

      <TabsContent value="database" className="flex-1 mt-0 overflow-hidden">
        <DatabaseOverview />
      </TabsContent>

      <TabsContent value="copilot" className="flex-1 mt-0 overflow-hidden">
        <ScrollArea className="h-full">
          <CopilotHistory />
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}
