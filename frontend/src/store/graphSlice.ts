import type { StateCreator } from "zustand";
import type { GraphEdge, GraphNode } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface GraphFilters {
  hidden_labels: string[];
  hidden_types: string[];
  collapsed_labels: string[];
}

export interface GraphSlice {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Cytoscape-managed positions, written back on layout completion / drag. */
  positions: Record<string, { x: number; y: number }>;
  filters: GraphFilters;

  addNodes: (nodes: GraphNode[]) => void;
  addEdges: (edges: GraphEdge[]) => void;
  removeNode: (id: string) => void;
  removeEdge: (id: string) => void;
  /** Merge incoming positions into the existing map (does not replace). */
  setPositions: (positions: Record<string, { x: number; y: number }>) => void;
  setFilters: (filters: Partial<GraphFilters>) => void;
  clearGraph: () => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createGraphSlice: StateCreator<
  GraphSlice,
  [],
  [],
  GraphSlice
> = (set) => ({
  nodes: [],
  edges: [],
  positions: {},
  filters: { hidden_labels: [], hidden_types: [], collapsed_labels: [] },

  addNodes: (incoming) =>
    set((state) => {
      const existingIds = new Set(state.nodes.map((n) => n.id));
      const newNodes = incoming.filter((n) => !existingIds.has(n.id));
      return { nodes: [...state.nodes, ...newNodes] };
    }),

  addEdges: (incoming) =>
    set((state) => {
      const existingIds = new Set(state.edges.map((e) => e.id));
      const newEdges = incoming.filter((e) => !existingIds.has(e.id));
      return { edges: [...state.edges, ...newEdges] };
    }),

  removeNode: (id) =>
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
      // Also remove edges that reference this node
      edges: state.edges.filter(
        (e) => e.source !== id && e.target !== id,
      ),
    })),

  removeEdge: (id) =>
    set((state) => ({
      edges: state.edges.filter((e) => e.id !== id),
    })),

  setPositions: (positions) =>
    set((state) => ({
      positions: { ...state.positions, ...positions },
    })),

  setFilters: (filters) =>
    set((state) => ({
      filters: { ...state.filters, ...filters },
    })),

  clearGraph: () =>
    set({
      nodes: [],
      edges: [],
      positions: {},
      filters: { hidden_labels: [], hidden_types: [], collapsed_labels: [] },
    }),
});
