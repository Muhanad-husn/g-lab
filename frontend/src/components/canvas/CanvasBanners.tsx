import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useStore } from "@/store";
import { CANVAS_WARN_AT, CANVAS_ERROR_AT } from "@/lib/constants";

/**
 * Absolute-positioned overlay showing guardrail warnings as the canvas fills.
 * - Warning  (yellow): ≥ 400 nodes — approaching limit
 * - Error    (red):    ≥ 500 nodes — hard limit reached
 * Both banners are individually dismissible. Dismissal resets automatically
 * when the node count drops back below the relevant threshold.
 */
export function CanvasBanners() {
  const nodeCount = useStore((s) => s.nodes.length);
  const [warnDismissed, setWarnDismissed] = useState(false);
  const [errorDismissed, setErrorDismissed] = useState(false);

  // Reset warning dismissal when count drops below warn threshold
  useEffect(() => {
    if (nodeCount < CANVAS_WARN_AT) setWarnDismissed(false);
  }, [nodeCount]);

  // Reset error dismissal when count drops below error threshold
  useEffect(() => {
    if (nodeCount < CANVAS_ERROR_AT) setErrorDismissed(false);
  }, [nodeCount]);

  const showWarn =
    nodeCount >= CANVAS_WARN_AT && nodeCount < CANVAS_ERROR_AT && !warnDismissed;
  const showError = nodeCount >= CANVAS_ERROR_AT && !errorDismissed;

  if (!showWarn && !showError) return null;

  return (
    // pointer-events-none on container so clicks pass through to the canvas
    <div className="pointer-events-none absolute inset-x-0 top-2 z-10 flex flex-col items-center gap-2">
      {showError && (
        <div className="pointer-events-auto flex items-center gap-2 rounded-md border border-red-700 bg-red-900/90 px-3 py-2 text-sm font-medium text-red-100 shadow-lg">
          <span>
            Canvas limit reached ({CANVAS_ERROR_AT} nodes). Further expansion is
            blocked.
          </span>
          <button
            onClick={() => setErrorDismissed(true)}
            className="ml-1 rounded p-0.5 hover:bg-red-700"
            aria-label="Dismiss error banner"
          >
            <X size={14} />
          </button>
        </div>
      )}
      {showWarn && (
        <div className="pointer-events-auto flex items-center gap-2 rounded-md border border-yellow-700 bg-yellow-900/90 px-3 py-2 text-sm font-medium text-yellow-100 shadow-lg">
          <span>
            Canvas nearing limit — {nodeCount}/{CANVAS_ERROR_AT} nodes. Consider
            filtering.
          </span>
          <button
            onClick={() => setWarnDismissed(true)}
            className="ml-1 rounded p-0.5 hover:bg-yellow-700"
            aria-label="Dismiss warning banner"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
