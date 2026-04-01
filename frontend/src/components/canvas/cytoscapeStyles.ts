import type cytoscape from "cytoscape";

// ─── Label color palette (indexed by hash of first label) ─────────────────────

const PALETTE = [
  "#4A90D9", // blue
  "#7B68EE", // medium slate blue
  "#50C878", // emerald green
  "#FF6B6B", // coral red
  "#FFB347", // mango orange
  "#40E0D0", // turquoise
  "#DDA0DD", // plum
  "#87CEEB", // sky blue
  "#F0E68C", // khaki
  "#98FB98", // pale green
] as const;

function hashLabel(label: string): number {
  let h = 0;
  for (let i = 0; i < label.length; i++) {
    h = (Math.imul(31, h) + label.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/** Pick a stable color from the palette based on the node's primary label. */
export function getLabelColor(labels: string[] | undefined | null): string {
  if (!labels || labels.length === 0) return PALETTE[0];
  return PALETTE[hashLabel(labels[0]) % PALETTE.length];
}

/**
 * Compute a human-readable display label from node properties.
 * Falls back to the primary label name, then "Node".
 */
export function getDisplayLabel(
  properties: Record<string, unknown> | undefined | null,
  labels: string[] | undefined | null,
): string {
  if (properties) {
    for (const key of ["_primary_value", "name", "title", "label", "id"]) {
      const val = properties[key];
      if (typeof val === "string" && val.length > 0) return val;
      if (typeof val === "number") return String(val);
    }
  }
  return labels?.[0] ?? "Node";
}

// ─── Cytoscape stylesheet ─────────────────────────────────────────────────────

export const CY_STYLESHEET: cytoscape.StylesheetStyle[] = [
  // ── Nodes ──────────────────────────────────────────────────────────────────
  {
    selector: "node",
    style: {
      "background-color": (ele: cytoscape.NodeSingular) =>
        (ele.data("labelColor") as string | undefined) ?? "#4A90D9",
      label: "data(displayLabel)",
      color: "#e2e8f0",
      "font-family": "Inter, system-ui, sans-serif",
      "font-size": 11,
      "font-weight": 500,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
      "text-max-width": "80px",
      "text-wrap": "ellipsis",
      width: 36,
      height: 36,
      shape: "ellipse",
      "border-width": 0,
      "min-zoomed-font-size": 8,
    },
  },
  // Selected node
  {
    selector: "node:selected",
    style: {
      "border-width": 3,
      "border-color": "#ffffff",
      "border-opacity": 0.9,
      "overlay-color": "#ffffff",
      "overlay-opacity": 0.1,
    },
  },

  // ── Edges ──────────────────────────────────────────────────────────────────
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#64748b",
      "target-arrow-color": "#64748b",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      label: "data(edgeLabel)",
      color: "#94a3b8",
      "font-size": 9,
      "text-rotation": "autorotate",
      "text-margin-y": -6,
      "min-zoomed-font-size": 8,
      opacity: 0.8,
    },
  },
  // Selected edge
  {
    selector: "edge:selected",
    style: {
      "line-color": "#94a3b8",
      "target-arrow-color": "#94a3b8",
      width: 2.5,
      opacity: 1,
    },
  },

  // ── Collapsed placeholders ────────────────────────────────────────────────
  {
    selector: "node.collapsed-placeholder",
    style: {
      shape: "diamond",
      width: 50,
      height: 50,
      "border-width": 2,
      "border-style": "dashed",
      "border-color": "#94a3b8",
      opacity: 0.85,
      "font-style": "italic",
    },
  },
  {
    selector: "edge.collapsed-placeholder",
    style: {
      "line-style": "dashed",
      opacity: 0.5,
    },
  },

  // ── Ghost elements (Phase 2 — AI-proposed, non-interactive) ───────────────
  {
    selector: "node.ghost",
    style: {
      opacity: 0.35,
      "border-style": "dashed",
      "border-width": 2,
      "border-color": "#94a3b8",
      events: "no",
    },
  },
  {
    selector: "edge.ghost",
    style: {
      opacity: 0.35,
      "line-style": "dashed",
      events: "no",
    },
  },
];
