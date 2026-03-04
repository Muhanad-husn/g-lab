import { useEffect, useRef, useState } from "react";
import type cytoscape from "cytoscape";
import { createCytoscapeInstance } from "@/lib/cytoscape";
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

    const instance = createCytoscapeInstance(containerRef.current);
    instance.style(CY_STYLESHEET);
    setCy(instance);

    // Notify Cytoscape when the panel is resized (react-resizable-panels)
    const observer = new ResizeObserver(() => {
      instance.resize();
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      instance.destroy();
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
