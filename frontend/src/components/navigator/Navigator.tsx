import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SearchPanel } from "./SearchPanel";
import { FilterPanel } from "./FilterPanel";
import { FindingsPanel } from "./FindingsPanel";
import { DatabaseOverview } from "./DatabaseOverview";

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
    </Tabs>
  );
}
