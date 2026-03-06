import { useEffect } from "react";
import { Toolbar } from "@/components/layout/Toolbar";
import { MainLayout } from "@/components/layout/MainLayout";
import { Navigator } from "@/components/navigator/Navigator";
import { Inspector } from "@/components/inspector/Inspector";
import { CytoscapeCanvas } from "@/components/canvas/CytoscapeCanvas";
import { CanvasBanners } from "@/components/canvas/CanvasBanners";
import { CanvasControls } from "@/components/canvas/CanvasControls";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { DevPanel } from "@/components/dev/DevPanel";
import { useSessionRestore } from "@/hooks/useSessionRestore";
import { useHealthPolling } from "@/hooks/useHealthPolling";
import { useReadOnlyMode } from "@/hooks/useReadOnlyMode";
import { usePresetRestore } from "@/hooks/usePresetRestore";
import { useDocumentActions } from "@/hooks/useDocumentActions";
import { getAttachedLibrary } from "@/api/documents";
import { useStore } from "@/store";

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  useSessionRestore();
  useHealthPolling();
  useReadOnlyMode();
  usePresetRestore();

  const { fetchLibraries } = useDocumentActions();
  const session = useStore((s) => s.session);
  const setAttachedLibrary = useStore((s) => s.setAttachedLibrary);

  // Load document libraries on mount
  useEffect(() => {
    void fetchLibraries();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restore attached library when session becomes available
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    void getAttachedLibrary(session.id).then((libraryId) => {
      if (!cancelled && libraryId) setAttachedLibrary(libraryId);
    });
    return () => {
      cancelled = true;
    };
  }, [session?.id, setAttachedLibrary]);

  return (
    <div className="flex h-screen flex-col bg-background text-foreground overflow-hidden">
      <Toolbar />
      <MainLayout
        navigator={<Navigator />}
        canvas={
          <div className="relative h-full w-full">
            <CytoscapeCanvas />
            <CanvasBanners />
            <CanvasControls />
          </div>
        }
        inspector={<Inspector />}
      />
      <ToastContainer />
      {import.meta.env.DEV && <DevPanel />}
    </div>
  );
}
