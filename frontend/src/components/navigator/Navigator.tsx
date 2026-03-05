import { useState } from "react";
import { Search, Filter, Bookmark, Database, Bot, FileText } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SearchPanel } from "./SearchPanel";
import { FilterPanel } from "./FilterPanel";
import { FindingsPanel } from "./FindingsPanel";
import { DatabaseOverview } from "./DatabaseOverview";
import { DocumentLibraryPanel } from "@/components/documents/DocumentLibraryPanel";
import { useStore } from "@/store";
import type { CopilotMessage } from "@/lib/types";

// ─── Tab definitions ─────────────────────────────────────────────────────────

const TABS = [
  { id: "search", icon: Search, label: "Search" },
  { id: "filters", icon: Filter, label: "Filters" },
  { id: "findings", icon: Bookmark, label: "Findings" },
  { id: "database", icon: Database, label: "Database" },
  { id: "copilot", icon: Bot, label: "Copilot" },
  { id: "documents", icon: FileText, label: "Documents" },
] as const;

type TabId = (typeof TABS)[number]["id"];

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
  const [activeTab, setActiveTab] = useState<TabId>("search");

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
                  ? "border-l-2 border-primary text-foreground"
                  : "border-l-2 border-transparent text-muted-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "search" && <SearchPanel />}
        {activeTab === "filters" && <FilterPanel />}
        {activeTab === "findings" && <FindingsPanel />}
        {activeTab === "database" && <DatabaseOverview />}
        {activeTab === "copilot" && (
          <ScrollArea className="h-full">
            <CopilotHistory />
          </ScrollArea>
        )}
        {activeTab === "documents" && <DocumentLibraryPanel />}
      </div>
    </div>
  );
}
