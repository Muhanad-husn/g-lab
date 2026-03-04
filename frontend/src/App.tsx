import { Toolbar } from "@/components/layout/Toolbar";
import { MainLayout } from "@/components/layout/MainLayout";
import { Navigator } from "@/components/navigator/Navigator";
import { Inspector } from "@/components/inspector/Inspector";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { DevPanel } from "@/components/dev/DevPanel";
import { useSessionRestore } from "@/hooks/useSessionRestore";
import { useHealthPolling } from "@/hooks/useHealthPolling";

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  useSessionRestore();
  useHealthPolling();

  return (
    <div className="flex h-screen flex-col bg-background text-foreground overflow-hidden">
      <Toolbar />
      <MainLayout
        navigator={<Navigator />}
        canvas={
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm select-none">
            Canvas — Stage 6
          </div>
        }
        inspector={<Inspector />}
      />
      <ToastContainer />
      {import.meta.env.DEV && <DevPanel />}
    </div>
  );
}
