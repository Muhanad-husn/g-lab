import { useEffect, useRef, useState } from "react";
import type cytoscape from "cytoscape";
import { createCytoscapeInstance } from "@/lib/cytoscape";
import { cytoscapeRef } from "@/lib/cytoscapeRef";
import { useStore } from "@/store";
import { HARD_LIMITS } from "@/lib/constants";
import { CY_STYLESHEET } from "./cytoscapeStyles";
import { useCanvasSync } from "./useCanvasSync";

/**
 * Mounts a Cytoscape instance into a full-size div, applies styles, attaches
 * the bi-directional sync hook, and handles container resize via ResizeObserver.
 */
export function CytoscapeCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  // Use state (not ref) so that useCanvasSync re-runs when cy becomes available
  const [cy, setCy] = useState<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const instance = createCytoscapeInstance(containerRef.current, CY_STYLESHEET);
    cytoscapeRef.current = instance;
    setCy(instance);

    // Notify Cytoscape when the panel is resized (react-resizable-panels)
    let hadZeroDimensions = true;
    const observer = new ResizeObserver((entries) => {
      instance.resize();
      // If container was 0-sized when nodes were added, refit after first real resize
      const entry = entries[0];
      if (hadZeroDimensions && entry) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          hadZeroDimensions = false;
          if (instance.nodes().length > 0) {
            instance.fit(undefined, 30);
          }
        }
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      instance.destroy();
      cytoscapeRef.current = null;
      setCy(null);
    };
  }, []);

  useCanvasSync(cy);

  const nodeCount = useStore((s) => s.nodes.length);
  const limit = HARD_LIMITS.MAX_CANVAS_NODES;
  const pct = nodeCount / limit;

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        className="h-full w-full"
        data-testid="cytoscape-canvas"
      />
      {nodeCount > 0 && (
        <div
          className={`absolute top-2 left-2 flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-mono select-none pointer-events-none backdrop-blur-sm ${
            pct >= 1
              ? "border-red-500/50 bg-red-950/70 text-red-300"
              : pct >= 0.8
                ? "border-yellow-500/40 bg-yellow-950/60 text-yellow-300"
                : "border-border/50 bg-card/70 text-muted-foreground"
          }`}
          title={`${nodeCount} of ${limit} nodes on canvas`}
        >
          <span>{nodeCount}</span>
          <span className="opacity-50">/</span>
          <span className="opacity-50">{limit}</span>
        </div>
      )}
    </div>
  );
}
