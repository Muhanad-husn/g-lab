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
  /** Optional bottom panel (Copilot). When provided, main content shrinks vertically. */
  bottomPanel?: React.ReactNode;
}

// ─── Resize handles ───────────────────────────────────────────────────────────

function HResizeHandle() {
  return (
    <PanelResizeHandle className="w-1 bg-border hover:bg-primary/40 transition-colors" />
  );
}

function VResizeHandle() {
  return (
    <PanelResizeHandle className="h-1 bg-border hover:bg-primary/40 transition-colors" />
  );
}

// ─── Main layout ──────────────────────────────────────────────────────────────

export function MainLayout({ navigator, canvas, inspector, bottomPanel }: MainLayoutProps) {
  const setPanelState = useStore((s) => s.setPanelState);

  const mainRow = (
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

      <HResizeHandle />

      {/* Canvas — fills remaining space */}
      <Panel className="bg-background relative">{canvas}</Panel>

      <HResizeHandle />

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

  if (!bottomPanel) {
    return mainRow;
  }

  return (
    <PanelGroup direction="vertical" className="flex-1 overflow-hidden">
      {/* Main content row */}
      <Panel defaultSize={72} minSize={40} className="flex overflow-hidden">
        {mainRow}
      </Panel>

      <VResizeHandle />

      {/* Bottom panel — Copilot, collapsible */}
      <Panel
        defaultSize={28}
        minSize={10}
        maxSize={50}
        collapsible
        className="flex flex-col bg-card overflow-hidden"
      >
        {bottomPanel}
      </Panel>
    </PanelGroup>
  );
}
