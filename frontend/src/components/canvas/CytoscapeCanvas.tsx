import { useEffect, useRef, useState } from "react";
import type cytoscape from "cytoscape";
import { createCytoscapeInstance } from "@/lib/cytoscape";
import { cytoscapeRef } from "@/lib/cytoscapeRef";
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

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      data-testid="cytoscape-canvas"
    />
  );
}
