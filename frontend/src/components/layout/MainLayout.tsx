import React, { useEffect, useRef } from "react";
import {
  type ImperativePanelHandle,
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { PanelLeftOpen, PanelRightOpen } from "lucide-react";
import { useStore } from "@/store";

interface MainLayoutProps {
  navigator: React.ReactNode;
  canvas: React.ReactNode;
  inspector: React.ReactNode;
}

// ─── Resize handle ────────────────────────────────────────────────────────────

function HResizeHandle() {
  return (
    <PanelResizeHandle className="w-1.5 bg-border hover:bg-primary/50 active:bg-primary/60 transition-colors" />
  );
}

// ─── Collapsed strip ─────────────────────────────────────────────────────────

function CollapsedStrip({
  side,
  onExpand,
}: {
  side: "left" | "right";
  onExpand: () => void;
}) {
  const Icon = side === "left" ? PanelLeftOpen : PanelRightOpen;
  return (
    <div className="flex flex-col items-center w-8 shrink-0 bg-card border-border py-2">
      <button
        onClick={onExpand}
        title={side === "left" ? "Expand navigator" : "Expand inspector"}
        className="p-1.5 rounded hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
      >
        <Icon className="h-4 w-4" />
      </button>
    </div>
  );
}

// ─── Main layout ──────────────────────────────────────────────────────────────

export function MainLayout({ navigator, canvas, inspector }: MainLayoutProps) {
  const setPanelState = useStore((s) => s.setPanelState);
  const navCollapsed = useStore((s) => s.panelStates.navigatorCollapsed);
  const inspCollapsed = useStore((s) => s.panelStates.inspectorCollapsed);

  const navRef = useRef<ImperativePanelHandle>(null);
  const inspRef = useRef<ImperativePanelHandle>(null);

  // Sync store → imperative panel API (for button-triggered collapse)
  useEffect(() => {
    if (navCollapsed) navRef.current?.collapse();
  }, [navCollapsed]);

  useEffect(() => {
    if (inspCollapsed) inspRef.current?.collapse();
  }, [inspCollapsed]);

  return (
    <PanelGroup direction="horizontal" className="flex-1 overflow-hidden">
      {/* Navigator — 20% default, min 15% */}
      <Panel
        ref={navRef}
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

      {navCollapsed && (
        <CollapsedStrip
          side="left"
          onExpand={() => navRef.current?.expand()}
        />
      )}

      <HResizeHandle />

      {/* Canvas — fills remaining space */}
      <Panel className="bg-background relative">{canvas}</Panel>

      <HResizeHandle />

      {inspCollapsed && (
        <CollapsedStrip
          side="right"
          onExpand={() => inspRef.current?.expand()}
        />
      )}

      {/* Inspector — 20% default, collapsible */}
      <Panel
        ref={inspRef}
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
