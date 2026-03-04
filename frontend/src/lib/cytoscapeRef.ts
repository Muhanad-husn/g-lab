import type cytoscape from "cytoscape";

/**
 * Module-level reference to the active Cytoscape instance.
 * Set by CytoscapeCanvas on mount; cleared on unmount.
 * Used by FindingsPanel to capture canvas snapshots without prop drilling.
 */
export const cytoscapeRef: { current: cytoscape.Core | null } = {
  current: null,
};

/**
 * Captures the current canvas as a PNG data URL.
 * Returns null if no Cytoscape instance is mounted or the canvas is empty.
 */
export function captureCanvasSnapshot(): string | null {
  if (!cytoscapeRef.current) return null;
  const dataUrl = cytoscapeRef.current.png({
    full: true,
    scale: 1.5,
    bg: "#0f0f0f",
  });
  return typeof dataUrl === "string" ? dataUrl : null;
}

/**
 * Strips the data URL prefix from a data URL returned by cy.png().
 * The backend expects raw base64 (no "data:image/png;base64," prefix).
 */
export function dataUrlToBase64(dataUrl: string): string {
  return dataUrl.replace(/^data:image\/png;base64,/, "");
}
