import cytoscape from "cytoscape";
import CoseBilkent from "cytoscape-cose-bilkent";

// Register CoSE-Bilkent layout extension (idempotent)
cytoscape.use(CoseBilkent);

export type LayoutName = "cose-bilkent" | "concentric" | "breadthfirst";

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
  breadthfirst: {
    name: "breadthfirst",
    fit: true,
    padding: 30,
    directed: false,
    animate: false,
    spacingFactor: 1.75,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
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
