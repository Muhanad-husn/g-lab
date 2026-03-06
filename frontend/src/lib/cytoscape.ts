import cytoscape from "cytoscape";
import CoseBilkent from "cytoscape-cose-bilkent";
import avsdf from "cytoscape-avsdf";
import cise from "cytoscape-cise";
import cola from "cytoscape-cola";
import euler from "cytoscape-euler";
import spread from "cytoscape-spread";
import dagre from "cytoscape-dagre";
import klay from "cytoscape-klay";

// Register layout extensions (idempotent)
cytoscape.use(CoseBilkent);
cytoscape.use(avsdf);
cytoscape.use(cise);
cytoscape.use(cola);
cytoscape.use(euler);
cytoscape.use(spread);
cytoscape.use(dagre);
cytoscape.use(klay);

export type LayoutName =
  | "cose-bilkent"
  | "concentric"
  | "grid"
  | "avsdf"
  | "cise"
  | "cola"
  | "euler"
  | "spread"
  | "dagre"
  | "klay";

export const LAYOUT_LABELS: Record<LayoutName, string> = {
  "cose-bilkent": "CoSE-Bilkent",
  concentric: "Concentric",
  grid: "Grid",
  avsdf: "AVSDF (Circular)",
  cise: "CiSE",
  cola: "Cola",
  euler: "Euler",
  spread: "Spread",
  dagre: "Dagre",
  klay: "Klay",
};

// Loose type to accommodate layout-specific options not in base LayoutOptions
type AnyLayoutOpts = Record<string, unknown>;

export const LAYOUT_CONFIGS: Record<LayoutName, AnyLayoutOpts> = {
  "cose-bilkent": {
    name: "cose-bilkent",
    quality: "default",
    animate: "end",
    animationDuration: 400,
    randomize: true,
    fit: true,
    padding: 30,
    nodeRepulsion: 4500,
    idealEdgeLength: 50,
    edgeElasticity: 0.45,
    nestingFactor: 0.1,
    gravity: 0.25,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 10,
    tilingPaddingHorizontal: 10,
  },
  concentric: {
    name: "concentric",
    fit: true,
    padding: 30,
    animate: false,
    minNodeSpacing: 10,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    concentric: (node: cytoscape.NodeSingular) => node.degree(false),
    levelWidth: (nodes: cytoscape.NodeCollection) =>
      Math.max(1, nodes.maxDegree(false) / 4),
  },
  grid: {
    name: "grid",
    fit: true,
    padding: 30,
    animate: false,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    rows: undefined,
    cols: undefined,
  },
  avsdf: {
    name: "avsdf",
    fit: true,
    padding: 30,
    animate: false,
    nodeSeparation: 60,
  },
  cise: {
    name: "cise",
    fit: true,
    padding: 30,
    animate: false,
    allowNodesInsideCircle: false,
    nodeSeparation: 12.5,
    idealInterClusterEdgeLengthCoefficient: 1.4,
  },
  cola: {
    name: "cola",
    fit: true,
    padding: 30,
    animate: false,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    randomize: false,
    maxSimulationTime: 4000,
    edgeLength: 100,
  },
  euler: {
    name: "euler",
    fit: true,
    padding: 30,
    animate: false,
    randomize: true,
    springLength: 80,
    springCoeff: 0.0008,
    gravity: -1.2,
    pull: 0.001,
    maxIterations: 1000,
    maxSimulationTime: 4000,
  },
  spread: {
    name: "spread",
    fit: true,
    padding: 30,
    animate: false,
    minDist: 20,
  },
  dagre: {
    name: "dagre",
    fit: true,
    padding: 30,
    animate: false,
    rankDir: "TB",
    nodeSep: 50,
    edgeSep: 10,
    rankSep: 50,
  },
  klay: {
    name: "klay",
    fit: true,
    padding: 30,
    animate: false,
    klay: {
      direction: "DOWN",
      spacing: 40,
      edgeSpacingFactor: 0.2,
    },
  },
};

export function createCytoscapeInstance(
  container: HTMLElement,
  style: cytoscape.StylesheetStyle[] = [],
): cytoscape.Core {
  return cytoscape({
    container,
    elements: [],
    style,
    userZoomingEnabled: true,
    userPanningEnabled: true,
    boxSelectionEnabled: true,
    minZoom: 0.1,
    maxZoom: 10,
  });
}

/**
 * Run a named layout on the cy instance.
 * @param incremental - True on expand: skip randomize + re-fit so existing nodes stay put.
 */
export function runLayout(
  cy: cytoscape.Core,
  name: LayoutName = "cose-bilkent",
  incremental = false,
): void {
  if (cy.nodes().length === 0) return;
  const config: AnyLayoutOpts = { ...LAYOUT_CONFIGS[name] };
  if (name === "cose-bilkent" && incremental) {
    config.randomize = false;
    config.fit = false;
    config.animate = false;
  }
  cy.layout(config as unknown as cytoscape.LayoutOptions).run();
}
