import {
  Search,
  Filter,
  Bookmark,
  Database,
  Bot,
  FileText,
  PanelLeftClose,
} from "lucide-react";
import { SearchPanel } from "./SearchPanel";
import { FilterPanel } from "./FilterPanel";
import { FindingsPanel } from "./FindingsPanel";
import { DatabaseOverview } from "./DatabaseOverview";
import { DocumentLibraryPanel } from "@/components/documents/DocumentLibraryPanel";
import { CopilotPanel } from "@/components/copilot/CopilotPanel";
import { useStore } from "@/store";

// ─── Tab definitions ─────────────────────────────────────────────────────────

const TABS = [
  { id: "database", icon: Database, label: "Database" },
  { id: "search", icon: Search, label: "Search" },
  { id: "filters", icon: Filter, label: "Filters" },
  { id: "copilot", icon: Bot, label: "Copilot" },
  { id: "findings", icon: Bookmark, label: "Findings" },
  { id: "documents", icon: FileText, label: "Documents" },
] as const;

// ─── Navigator ────────────────────────────────────────────────────────────────

export function Navigator() {
  const activeTab = useStore((s) => s.navigatorTab);
  const setActiveTab = useStore((s) => s.setNavigatorTab);
  const setPanelState = useStore((s) => s.setPanelState);

  return (
    <div className="flex flex-row h-full">
      {/* Vertical icon sidebar */}
      <div className="flex flex-col w-10 shrink-0 border-r border-border bg-card">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              title={tab.label}
              className={`w-10 h-10 flex items-center justify-center transition-colors hover:bg-accent/50 ${
                isActive
                  ? "border-l-2 border-primary text-foreground bg-primary/10"
                  : "border-l-2 border-transparent text-muted-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          );
        })}

        {/* Collapse button at bottom */}
        <div className="mt-auto">
          <button
            onClick={() => setPanelState("navigatorCollapsed", true)}
            title="Collapse navigator"
            className="w-10 h-10 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "search" && <SearchPanel />}
        {activeTab === "filters" && <FilterPanel />}
        {activeTab === "findings" && <FindingsPanel />}
        {activeTab === "database" && <DatabaseOverview />}
        {activeTab === "copilot" && <CopilotPanel />}
        {activeTab === "documents" && <DocumentLibraryPanel />}
      </div>
    </div>
  );
}
