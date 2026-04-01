import { useEffect } from "react";
import type cytoscape from "cytoscape";
import type { GraphNode } from "@/lib/types";
import { runLayout } from "@/lib/cytoscape";
import { useStore } from "@/store";
import { useGraphActions } from "@/hooks/useGraphActions";
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
  const collapsedNodeIds = useStore((s) => s.collapsedNodeIds);
  const setPositions = useStore((s) => s.setPositions);
  const setSelectedIds = useStore((s) => s.setSelectedIds);
  const clearSelection = useStore((s) => s.clearSelection);
  const { expandNode } = useGraphActions();

  // ─── Inbound sync: store → cy ──────────────────────────────────────────────
  useEffect(() => {
    if (!cy) return;

    // Compute delta between current cy state and the store
    // Exclude collapsed placeholders from diff — they are managed by filter sync
    const currentNodeIds = new Set(
      cy.nodes().filter((n) => !n.hasClass("collapsed-placeholder")).map((n) => n.id()),
    );
    const currentEdgeIds = new Set(
      cy.edges().filter((e) => !e.hasClass("collapsed-placeholder")).map((e) => e.id()),
    );
    const storeNodeIds = new Set(nodes.map((n) => n.id));
    const storeEdgeIds = new Set(edges.map((e) => e.id));

    const nodesToAdd = nodes.filter((n) => !currentNodeIds.has(n.id));
    const edgesToAdd = edges.filter((e) => !currentEdgeIds.has(e.id));
    const nodesToRemove = cy
      .nodes()
      .filter((n) => !n.hasClass("collapsed-placeholder") && !storeNodeIds.has(n.id()));
    const edgesToRemove = cy
      .edges()
      .filter((e) => !e.hasClass("collapsed-placeholder") && !storeEdgeIds.has(e.id()));

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
        const id = n.id();
        // Skip collapsed placeholders and proxy edges
        if (id.startsWith("__collapsed__") || id.startsWith("__proxy__")) return;
        positions[id] = n.position();
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
        // Ignore taps on collapsed placeholders
        if (el.hasClass("collapsed-placeholder")) return;
        const id = el.id();
        const original = evt.originalEvent as MouseEvent | undefined;
        if (original && (original.ctrlKey || original.metaKey)) {
          // Ctrl/Cmd+click: toggle element in multi-selection
          const prev = useStore.getState().selectedIds;
          if (prev.includes(id)) {
            setSelectedIds(prev.filter((s) => s !== id));
          } else {
            setSelectedIds([...prev, id]);
          }
        } else {
          setSelectedIds([id]);
        }
      }
    };

    cy.on("tap", handleTap);
    return () => {
      cy.off("tap", handleTap);
    };
  }, [cy, setSelectedIds, clearSelection]);

  // ─── Double-click to expand: cy dbltap → expandNode ─────────────────────────
  useEffect(() => {
    if (!cy) return;
    const handleDblTap = (evt: cytoscape.EventObject) => {
      const el = evt.target as cytoscape.SingularElementArgument;
      if (el.hasClass("collapsed-placeholder")) return;
      void expandNode(el.id(), { hops: 1 });
    };
    cy.on("dbltap", "node", handleDblTap);
    return () => {
      cy.off("dbltap", "node", handleDblTap);
    };
  }, [cy, expandNode]);

  // ─── Per-node collapse: collapsedNodeIds → cy display:none ────────────────
  useEffect(() => {
    if (!cy) return;
    const hiddenSet = new Set(collapsedNodeIds);
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        if (n.hasClass("collapsed-placeholder")) return;
        if (hiddenSet.has(n.id())) {
          n.style("display", "none");
          n.connectedEdges().style("display", "none");
        }
      });
      // Unhide nodes no longer in collapsed set (only real nodes, not label-collapsed)
      cy.nodes().forEach((n) => {
        if (n.hasClass("collapsed-placeholder")) return;
        if (!hiddenSet.has(n.id()) && n.style("display") === "none") {
          // Check if this node is hidden by label filters — if so, leave it hidden
          const labels = n.data("labels") as string[];
          const labelHidden = labels.some((l: string) => filters.hidden_labels.includes(l));
          const labelCollapsed = labels.some((l: string) =>
            (filters.collapsed_labels ?? []).includes(l),
          );
          if (!labelHidden && !labelCollapsed) {
            n.style("display", "element");
            n.connectedEdges().forEach((e) => {
              const otherNode = e.source().id() === n.id() ? e.target() : e.source();
              if (otherNode.style("display") !== "none") {
                e.style("display", "element");
              }
            });
          }
        }
      });
    });
  }, [cy, collapsedNodeIds, filters]);

  // ─── Filter sync: store filters → cy visibility + collapse placeholders ───
  // Note: hide()/show() are not in @types/cytoscape; use style('display',...).
  useEffect(() => {
    if (!cy) return;

    cy.batch(() => {
      // 1. Remove previous placeholders
      cy.remove(".collapsed-placeholder");

      // Partition real nodes (not ghost) into hidden / collapsed / visible
      const realNodes = cy.nodes().filter((n) => !n.hasClass("ghost"));
      const hiddenSet = new Set(filters.hidden_labels);
      const collapsedSet = new Set(filters.collapsed_labels);

      const hiddenNodes = realNodes.filter((n) => {
        const labels = n.data("labels") as string[];
        return labels.some((l) => hiddenSet.has(l));
      });
      const hiddenNodeIds = new Set(hiddenNodes.map((n) => n.id()));

      const collapsedNodes = realNodes.filter((n) => {
        if (hiddenNodeIds.has(n.id())) return false;
        const labels = n.data("labels") as string[];
        return labels.some((l) => collapsedSet.has(l));
      });
      const collapsedNodeIds = new Set(collapsedNodes.map((n) => n.id()));

      // 2. Apply display styles to real nodes
      hiddenNodes.style("display", "none");
      collapsedNodes.style("display", "none");
      realNodes
        .filter((n) => !hiddenNodeIds.has(n.id()) && !collapsedNodeIds.has(n.id()))
        .style("display", "element");

      // 3. Create placeholder nodes for each collapsed label
      const invisibleNodeIds = new Set([...hiddenNodeIds, ...collapsedNodeIds]);

      for (const label of filters.collapsed_labels) {
        // Gather nodes that belong to this collapsed label (and aren't already hidden)
        const nodesForLabel = collapsedNodes.filter((n) => {
          const labels = n.data("labels") as string[];
          return labels.includes(label);
        });
        if (nodesForLabel.length === 0) continue;

        // Compute centroid position
        let cx = 0;
        let cy2 = 0;
        nodesForLabel.forEach((n) => {
          const pos = n.position();
          cx += pos.x;
          cy2 += pos.y;
        });
        cx /= nodesForLabel.length;
        cy2 /= nodesForLabel.length;

        const firstColor = nodesForLabel[0].data("labelColor") as string;
        const placeholderId = `__collapsed__${label}`;

        cy.add({
          group: "nodes",
          data: {
            id: placeholderId,
            displayLabel: `${label} (${nodesForLabel.length})`,
            labelColor: firstColor,
            labels: [label],
          },
          position: { x: cx, y: cy2 },
          classes: "collapsed-placeholder",
        });

        // 4. Create proxy edges: scan edges of collapsed nodes
        const proxyEdgeSet = new Set<string>();
        nodesForLabel.forEach((n) => {
          n.connectedEdges().forEach((e) => {
            const srcId = e.source().id();
            const tgtId = e.target().id();
            const edgeType = e.data("type") as string;

            // Determine the "other" endpoint
            const otherId = srcId === n.id() ? tgtId : srcId;

            // Only create proxy if the other end is visible (not collapsed/hidden)
            if (invisibleNodeIds.has(otherId)) return;

            const proxyKey = `${placeholderId}|${otherId}|${edgeType}`;
            if (proxyEdgeSet.has(proxyKey)) return;
            proxyEdgeSet.add(proxyKey);

            const proxyEdgeId = `__proxy__${placeholderId}__${otherId}__${edgeType}`;
            cy.add({
              group: "edges",
              data: {
                id: proxyEdgeId,
                source: srcId === n.id() ? placeholderId : otherId,
                target: tgtId === n.id() ? placeholderId : otherId,
                type: edgeType,
                edgeLabel: edgeType,
              },
              classes: "collapsed-placeholder",
            });
          });
        });
      }

      // 5. Edge visibility: hide edges whose type is filtered OR whose endpoint is invisible
      const allRealEdges = cy.edges().not(".collapsed-placeholder");
      const edgeHidden = allRealEdges.filter((e: cytoscape.EdgeSingular) => {
        const typeHidden = filters.hidden_types.includes(e.data("type") as string);
        const nodeHidden =
          invisibleNodeIds.has(e.source().id()) ||
          invisibleNodeIds.has(e.target().id());
        return typeHidden || nodeHidden;
      });

      edgeHidden.style("display", "none");
      allRealEdges.not(edgeHidden).style("display", "element");
    });
  }, [cy, filters]);
}
