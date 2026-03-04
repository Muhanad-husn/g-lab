import { useEffect } from "react";
import { Toolbar } from "@/components/layout/Toolbar";
import { MainLayout } from "@/components/layout/MainLayout";
import { Navigator } from "@/components/navigator/Navigator";
import { Inspector } from "@/components/inspector/Inspector";
import { CytoscapeCanvas } from "@/components/canvas/CytoscapeCanvas";
import { CanvasBanners } from "@/components/canvas/CanvasBanners";
import { CopilotPanel } from "@/components/copilot/CopilotPanel";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { DevPanel } from "@/components/dev/DevPanel";
import { useSessionRestore } from "@/hooks/useSessionRestore";
import { useHealthPolling } from "@/hooks/useHealthPolling";
import { useReadOnlyMode } from "@/hooks/useReadOnlyMode";
import { getPresets } from "@/api/config";
import { useStore } from "@/store";

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  useSessionRestore();
  useHealthPolling();
  useReadOnlyMode();

  const setPresets = useStore((s) => s.setPresets);

  // Load backend presets once on mount
  useEffect(() => {
    getPresets()
      .then(setPresets)
      .catch(() => {
        // Presets unavailable (copilot unconfigured) — non-fatal
      });
  }, [setPresets]);

  return (
    <div className="flex h-screen flex-col bg-background text-foreground overflow-hidden">
      <Toolbar />
      <MainLayout
        navigator={<Navigator />}
        canvas={
          <div className="relative h-full w-full">
            <CytoscapeCanvas />
            <CanvasBanners />
          </div>
        }
        inspector={<Inspector />}
        bottomPanel={<CopilotPanel />}
      />
      <ToastContainer />
      {import.meta.env.DEV && <DevPanel />}
    </div>
  );
}
