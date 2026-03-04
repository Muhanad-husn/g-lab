import React from "react";
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { useStore } from "@/store";

interface MainLayoutProps {
  navigator: React.ReactNode;
  canvas: React.ReactNode;
  inspector: React.ReactNode;
}

// ─── Resize handle ────────────────────────────────────────────────────────────

function ResizeHandle() {
  return (
    <PanelResizeHandle className="w-1 bg-border hover:bg-primary/40 transition-colors" />
  );
}

// ─── Main layout ──────────────────────────────────────────────────────────────

export function MainLayout({ navigator, canvas, inspector }: MainLayoutProps) {
  const setPanelState = useStore((s) => s.setPanelState);

  return (
    <PanelGroup direction="horizontal" className="flex-1 overflow-hidden">
      {/* Navigator — 20% default, min 15% */}
      <Panel
        defaultSize={20}
        minSize={15}
        maxSize={35}
        onCollapse={() => setPanelState("navigatorCollapsed", true)}
        onExpand={() => setPanelState("navigatorCollapsed", false)}
        collapsible
        className="flex flex-col bg-card"
      >
        {navigator}
      </Panel>

      <ResizeHandle />

      {/* Canvas — fills remaining space */}
      <Panel className="bg-background relative">{canvas}</Panel>

      <ResizeHandle />

      {/* Inspector — 20% default, collapsible */}
      <Panel
        defaultSize={20}
        minSize={15}
        maxSize={35}
        onCollapse={() => setPanelState("inspectorCollapsed", true)}
        onExpand={() => setPanelState("inspectorCollapsed", false)}
        collapsible
        className="flex flex-col bg-card"
      >
        {inspector}
      </Panel>
    </PanelGroup>
  );
}
