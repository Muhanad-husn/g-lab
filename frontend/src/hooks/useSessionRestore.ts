import { useEffect } from "react";
import { getLastActive } from "@/api/sessions";
import { listFindings } from "@/api/findings";
import { getHistory } from "@/api/copilot";
import { getOverview } from "@/api/graph";
import { useStore } from "@/store";

/**
 * On mount, fetches the last-active session and populates the session +
 * findings + conversation history slices. Also fetches the database
 * overview (non-critical).
 *
 * Mount once in App.tsx.
 */
export function useSessionRestore(): void {
  const setSession = useStore((s) => s.setSession);
  const setFindings = useStore((s) => s.setFindings);
  const setDbOverview = useStore((s) => s.setDbOverview);
  const loadHistory = useStore((s) => s.loadHistory);

  useEffect(() => {
    let cancelled = false;

    async function restore(): Promise<void> {
      const session = await getLastActive();
      if (cancelled || !session) return;

      setSession(session);

      try {
        const findings = await listFindings(session.id);
        if (!cancelled) setFindings(findings);
      } catch {
        // Findings fetch failure is non-critical — session still usable.
      }

      try {
        const messages = await getHistory(session.id);
        if (!cancelled) loadHistory(messages);
      } catch {
        // History fetch failure is non-critical.
      }

      try {
        const overview = await getOverview();
        if (!cancelled) setDbOverview(overview);
      } catch {
        // Overview fetch failure is non-critical.
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, [setSession, setFindings, setDbOverview, loadHistory]);
}
