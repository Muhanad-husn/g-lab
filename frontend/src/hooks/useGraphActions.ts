import { useStore } from "@/store";
import { expand, findPaths as findPathsApi } from "@/api/graph";
import { ApiRequestError } from "@/api/client";
import { cytoscapeRef } from "@/lib/cytoscapeRef";
import type { ExpandResponse, GuardrailDetail, PathResponse } from "@/lib/types";

/**
 * Bridge hook: wraps graph API calls with store dispatch and guardrail-banner
 * handling. Components call these actions instead of the raw API directly.
 *
 * All functions read the current canvas node count at call time (via
 * useStore.getState()) so freshly-added nodes are always reflected in the
 * current_canvas_count sent to the backend.
 */
export function useGraphActions() {
  const addNodes = useStore((s) => s.addNodes);
  const addEdges = useStore((s) => s.addEdges);
  const pushBanner = useStore((s) => s.pushBanner);
  const presetConfig = useStore((s) => s.presetConfig);

  /**
   * Expand outward from a node already on the canvas.
   * On 409 guardrail violation, pushes an error banner instead of throwing.
   */
  async function expandNode(
    nodeId: string,
    opts?: { hops?: number; rel_types?: string[] | null },
  ): Promise<ExpandResponse | null> {
    // Read current count and session_id synchronously at call time
    const state = useStore.getState();
    const currentCount = state.nodes.length;
    const sessionId = state.session?.id ?? null;
    try {
      const { data, warnings } = await expand({
        node_ids: [nodeId],
        relationship_types: opts?.rel_types ?? null,
        hops: opts?.hops ?? presetConfig.default_hops,
        limit: presetConfig.default_expansion_limit,
        current_canvas_count: currentCount,
        session_id: sessionId,
      });
      addNodes(data.nodes);
      addEdges(data.edges);
      for (const w of warnings) pushBanner({ level: "warning", message: w });
      return data;
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 409) {
        const detail = err.detail as GuardrailDetail | undefined;
        const msg = detail
          ? `Canvas limit reached (${detail.current}/${detail.hard_limit} nodes). Remove nodes to expand further.`
          : (err as Error).message;
        pushBanner({ level: "error", message: msg });
        return null;
      }
      throw err;
    }
  }

  /**
   * Convenience wrapper: expand from a freshly-seeded node using preset defaults.
   * Used by SearchPanel's "Add & Expand" action.
   */
  async function searchAndSeed(nodeId: string): Promise<ExpandResponse | null> {
    return expandNode(nodeId);
  }

  /**
   * Find shortest paths between two canvas nodes and add them to the canvas.
   * On 409 guardrail violation, pushes an error banner instead of throwing.
   */
  async function findPaths(
    sourceId: string,
    targetId: string,
    opts?: { max_hops?: number },
  ): Promise<PathResponse | null> {
    const state = useStore.getState();
    const currentCount = state.nodes.length;
    const sessionId = state.session?.id ?? null;
    try {
      const { data, warnings } = await findPathsApi({
        source_id: sourceId,
        target_id: targetId,
        max_hops: opts?.max_hops ?? presetConfig.default_hops,
        current_canvas_count: currentCount,
        session_id: sessionId,
      });
      addNodes(data.nodes);
      addEdges(data.edges);
      for (const w of warnings) pushBanner({ level: "warning", message: w });
      return data;
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 409) {
        const detail = err.detail as GuardrailDetail | undefined;
        const msg = detail
          ? `Canvas limit reached (${detail.current}/${detail.hard_limit} nodes). Remove nodes to find paths.`
          : (err as Error).message;
        pushBanner({ level: "error", message: msg });
        return null;
      }
      throw err;
    }
  }

  /**
   * Accept the Copilot-proposed graph delta.
   * Promotes ghost elements on the canvas to real elements, then merges
   * the delta nodes/edges into graphSlice and clears pendingDelta.
   */
  function acceptCopilotDelta(): void {
    const cy = cytoscapeRef.current;
    if (cy) {
      // Promote ghost elements → real (remove dashed style, make interactive)
      cy.elements(".ghost").removeClass("ghost");
    }
    // Cross-slice action: adds delta to graphSlice and clears pendingDelta
    useStore.getState().acceptDelta();
  }

  return { expandNode, searchAndSeed, findPaths, acceptCopilotDelta };
}
