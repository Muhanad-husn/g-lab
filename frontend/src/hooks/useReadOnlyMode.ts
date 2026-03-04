/**
 * Tracks Neo4j degraded/disconnected state and shows a persistent canvas
 * banner when graph operations are unavailable.
 *
 * Returns true when in read-only mode (Neo4j unavailable).
 *
 * Mount once in App.tsx — works alongside useHealthPolling which handles
 * the actual polling and toast notifications on status transitions.
 *
 * ```tsx
 * function App() {
 *   useHealthPolling();
 *   useReadOnlyMode();
 *   return <MainLayout />;
 * }
 * ```
 */
import { useEffect, useRef } from "react";
import { useStore } from "@/store";

export function useReadOnlyMode(): boolean {
  const neo4jStatus = useStore((s) => s.neo4jStatus);
  const isReadOnly =
    neo4jStatus === "degraded" || neo4jStatus === "disconnected";
  const bannerIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (isReadOnly && !bannerIdRef.current) {
      // Push a persistent error banner (duration handled by CanvasBanners dismiss)
      bannerIdRef.current = useStore.getState().pushBanner({
        level: "error",
        message:
          "Neo4j unavailable — graph operations are disabled. Read-only mode active.",
      });
    } else if (!isReadOnly && bannerIdRef.current) {
      useStore.getState().dismissBanner(bannerIdRef.current);
      bannerIdRef.current = null;
    }
  }, [isReadOnly]);

  // Dismiss banner if this hook unmounts (e.g., during testing)
  useEffect(() => {
    return () => {
      if (bannerIdRef.current) {
        useStore.getState().dismissBanner(bannerIdRef.current);
        bannerIdRef.current = null;
      }
    };
  }, []);

  return isReadOnly;
}
