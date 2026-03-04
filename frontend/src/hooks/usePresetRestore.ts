import { useEffect } from "react";
import { getPresets } from "@/api/config";
import { useStore } from "@/store";

/**
 * On mount, loads backend presets and populates configSlice.presets.
 * Non-fatal if the fetch fails (copilot may be unconfigured).
 *
 * Mount once in App.tsx.
 */
export function usePresetRestore(): void {
  const setPresets = useStore((s) => s.setPresets);

  useEffect(() => {
    let cancelled = false;

    getPresets()
      .then((presets) => {
        if (!cancelled) setPresets(presets);
      })
      .catch(() => {
        // Presets unavailable (copilot unconfigured) — non-fatal.
      });

    return () => {
      cancelled = true;
    };
  }, [setPresets]);
}
