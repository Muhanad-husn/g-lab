import { useEffect } from "react";
import type cytoscape from "cytoscape";
import type { GraphNode } from "@/lib/types";
import { runLayout } from "@/lib/cytoscape";
import { useStore } from "@/store";
import { getLabelColor, getDisplayLabel } from "./cytoscapeStyles";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Build the cy element data payload from a store GraphNode. */
function nodeToCyData(node: GraphNode): Record<string, unknown> {
  return {
    id: node.id,
    labels: node.labels,
    displayLabel: getDisplayLabel(node.properties, node.labels),
    labelColor: getLabelColor(node.labels),
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Bi-directional sync between Zustand (graphSlice / uiSlice) and a live
 * Cytoscape instance. Safe to call with `cy = null` before the canvas mounts.
 *
 * Responsibilities:
 * - **Inbound:** store nodes/edges → cy (diff, batch add/remove, run layout)
 * - **Outbound:** layoutstop/dragfree → setPositions (debounced 200 ms on drag)
 * - **Selection:** cy tap → uiSlice.setSelectedIds / clearSelection
 * - **Filters:** store filters → cy hide/show by label and relationship type
 */
export function useCanvasSync(cy: cytoscape.Core | null): void {
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const filters = useStore((s) => s.filters);
  const pendingDelta = useStore((s) => s.pendingDelta);
  const setPositions = useStore((s) => s.setPositions);
  const setSelectedIds = useStore((s) => s.setSelectedIds);
  const clearSelection = useStore((s) => s.clearSelection);

  // ─── Inbound sync: store → cy ──────────────────────────────────────────────
  useEffect(() => {
    if (!cy) return;

    // Compute delta between current cy state and the store
    const currentNodeIds = new Set(cy.nodes().map((n) => n.id()));
    const currentEdgeIds = new Set(cy.edges().map((e) => e.id()));
    const storeNodeIds = new Set(nodes.map((n) => n.id));
    const storeEdgeIds = new Set(edges.map((e) => e.id));

    const nodesToAdd = nodes.filter((n) => !currentNodeIds.has(n.id));
    const edgesToAdd = edges.filter((e) => !currentEdgeIds.has(e.id));
    const nodesToRemove = cy.nodes().filter((n) => !storeNodeIds.has(n.id()));
    const edgesToRemove = cy.edges().filter((e) => !storeEdgeIds.has(e.id()));

    const hasChanges =
      nodesToAdd.length > 0 ||
      edgesToAdd.length > 0 ||
      nodesToRemove.length > 0 ||
      edgesToRemove.length > 0;

    if (!hasChanges) return;

    // Track whether we had existing nodes before this update (expand scenario)
    const wasEmpty = currentNodeIds.size === 0;

    cy.batch(() => {
      // Remove stale elements (removing a node auto-removes its edges in cy)
      nodesToRemove.remove();
      edgesToRemove.remove();

      // Add new nodes first so edge source/target IDs always resolve
      nodesToAdd.forEach((node) => {
        cy.add({
          group: "nodes",
          data: nodeToCyData(node),
          // Use stored position if available; layout will reposition anyway
          position: node.position ?? { x: 0, y: 0 },
        });
      });

      edgesToAdd.forEach((edge) => {
        cy.add({
          group: "edges",
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: edge.type,
            edgeLabel: edge.type,
          },
        });
      });
    });

    // Re-layout only when nodes were added; incremental = already had nodes
    if (nodesToAdd.length > 0) {
      runLayout(cy, "cose-bilkent", !wasEmpty);
    }
  }, [cy, nodes, edges]);

  // ─── Outbound sync: cy positions → store ───────────────────────────────────
  useEffect(() => {
    if (!cy) return;

    const writeAllPositions = () => {
      const positions: Record<string, { x: number; y: number }> = {};
      cy.nodes().forEach((n) => {
        positions[n.id()] = n.position();
      });
      setPositions(positions);
    };

    let dragTimer: ReturnType<typeof setTimeout> | undefined;
    const handleDragFree = () => {
      clearTimeout(dragTimer);
      dragTimer = setTimeout(writeAllPositions, 200);
    };

    // After layout completes: capture final positions immediately
    cy.on("layoutstop", writeAllPositions);
    // After user drag ends: debounce to avoid rapid-fire store updates
    cy.on("dragfree", "node", handleDragFree);

    return () => {
      cy.off("layoutstop", writeAllPositions);
      cy.off("dragfree", "node", handleDragFree);
      clearTimeout(dragTimer);
    };
  }, [cy, setPositions]);

  // ─── Selection sync: cy tap → uiSlice ─────────────────────────────────────
  useEffect(() => {
    if (!cy) return;

    const handleTap = (evt: cytoscape.EventObject) => {
      if (evt.target === cy) {
        // Tapped the canvas background → deselect all
        clearSelection();
      } else {
        const el = evt.target as cytoscape.SingularElementArgument;
        setSelectedIds([el.id()]);
      }
    };

    cy.on("tap", handleTap);
    return () => {
      cy.off("tap", handleTap);
    };
  }, [cy, setSelectedIds, clearSelection]);

  // ─── Ghost sync: pendingDelta → cy ghost elements ─────────────────────────
  // Adds proposed nodes/edges with the `.ghost` class when a delta arrives.
  // On Accept: DeltaPreview calls cy.removeClass('ghost') before acceptDelta().
  // On Discard: DeltaPreview calls cy.remove('.ghost') before clearPendingDelta().
  // Cleanup (effect teardown) removes any leftover ghosts when delta clears.
  useEffect(() => {
    if (!cy || !pendingDelta) return;

    let ghostsAdded = 0;

    cy.batch(() => {
      for (const node of pendingDelta.add_nodes) {
        if (!cy.getElementById(node.id).length) {
          cy.add({
            group: "nodes",
            data: nodeToCyData(node),
            position: node.position ?? { x: 0, y: 0 },
          }).addClass("ghost");
          ghostsAdded++;
        }
      }

      for (const edge of pendingDelta.add_edges) {
        if (!cy.getElementById(edge.id).length) {
          cy.add({
            group: "edges",
            data: {
              id: edge.id,
              source: edge.source,
              target: edge.target,
              type: edge.type,
              edgeLabel: edge.type,
            },
          }).addClass("ghost");
        }
      }
    });

    if (ghostsAdded > 0) {
      runLayout(cy, "cose-bilkent", true);
    }

    return () => {
      // Remove any remaining ghost elements (fires on delta change or unmount)
      cy.remove(".ghost");
    };
  }, [cy, pendingDelta]);

  // ─── Filter sync: store filters → cy visibility ───────────────────────────
  // Note: hide()/show() are not in @types/cytoscape; use style('display',...).
  useEffect(() => {
    if (!cy) return;

    cy.batch(() => {
      const labelHidden = cy.nodes().filter((n) => {
        const labels = n.data("labels") as string[];
        return labels.some((l) => filters.hidden_labels.includes(l));
      });
      const labelHiddenIds = new Set(labelHidden.map((n) => n.id()));

      labelHidden.style("display", "none");
      cy.nodes().not(labelHidden).style("display", "element");

      // Hide edges whose type is filtered OR whose endpoint node is hidden
      const edgeHidden = cy.edges().filter((e) => {
        const typeHidden = filters.hidden_types.includes(
          e.data("type") as string,
        );
        const nodeHidden =
          labelHiddenIds.has(e.source().id()) ||
          labelHiddenIds.has(e.target().id());
        return typeHidden || nodeHidden;
      });

      edgeHidden.style("display", "none");
      cy.edges().not(edgeHidden).style("display", "element");
    });
  }, [cy, filters]);
}
