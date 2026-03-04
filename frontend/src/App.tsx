import { Toolbar } from "@/components/layout/Toolbar";
import { MainLayout } from "@/components/layout/MainLayout";
import { Navigator } from "@/components/navigator/Navigator";
import { Inspector } from "@/components/inspector/Inspector";
import { CytoscapeCanvas } from "@/components/canvas/CytoscapeCanvas";
import { CanvasBanners } from "@/components/canvas/CanvasBanners";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { DevPanel } from "@/components/dev/DevPanel";
import { useSessionRestore } from "@/hooks/useSessionRestore";
import { useHealthPolling } from "@/hooks/useHealthPolling";
import { useReadOnlyMode } from "@/hooks/useReadOnlyMode";

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  useSessionRestore();
  useHealthPolling();
  useReadOnlyMode();

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
      />
      <ToastContainer />
      {import.meta.env.DEV && <DevPanel />}
    </div>
  );
}
