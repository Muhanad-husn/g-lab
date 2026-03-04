// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useStore } from "@/store";
import { Inspector } from "@/components/inspector/Inspector";

// Mock useGraphActions to prevent real API calls from NodeDetail
vi.mock("@/hooks/useGraphActions", () => ({
  useGraphActions: () => ({
    expandNode: vi.fn(),
    searchAndSeed: vi.fn(),
    findPaths: vi.fn(),
  }),
}));

// ─── Inspector component tests ────────────────────────────────────────────────

describe("Inspector", () => {
  beforeEach(() => {
    // Reset store to initial state between tests (true = replace, not merge)
    useStore.setState(useStore.getInitialState(), true);
  });

  it("shows placeholder when nothing is selected", () => {
    render(<Inspector />);
    expect(
      screen.getByText(/select a node or relationship/i),
    ).toBeInTheDocument();
  });

  it("renders NodeDetail when a node is selected", () => {
    useStore.setState({
      nodes: [{ id: "n1", labels: ["Person"], properties: { name: "Alice" } }],
      selectedIds: ["n1"],
    });
    render(<Inspector />);
    expect(screen.getByText("Person")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders EdgeDetail when an edge is selected", () => {
    useStore.setState({
      edges: [
        { id: "e1", type: "KNOWS", source: "n1", target: "n2", properties: {} },
      ],
      selectedIds: ["e1"],
    });
    render(<Inspector />);
    expect(screen.getByText("KNOWS")).toBeInTheDocument();
  });

  it("shows not-found message when selected id is unknown", () => {
    useStore.setState({ selectedIds: ["ghost-id"], nodes: [], edges: [] });
    render(<Inspector />);
    expect(screen.getByText(/element not found in canvas/i)).toBeInTheDocument();
  });
});
