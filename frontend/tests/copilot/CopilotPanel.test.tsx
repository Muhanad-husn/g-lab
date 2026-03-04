// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useStore } from "@/store";

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockStartSSE = vi.fn().mockResolvedValue(undefined);
const mockStopSSE = vi.fn();

vi.mock("@/hooks/useSSE", () => ({
  useSSE: () => ({ start: mockStartSSE, stop: mockStopSSE }),
}));

vi.mock("@/hooks/useReadOnlyMode", () => ({
  useReadOnlyMode: () => false,
}));

vi.mock("@/hooks/useGraphActions", () => ({
  useGraphActions: () => ({
    expandNode: vi.fn(),
    searchAndSeed: vi.fn(),
    findPaths: vi.fn(),
    acceptCopilotDelta: vi.fn(),
  }),
}));

// Import after mocks are registered
import { CopilotPanel } from "@/components/copilot/CopilotPanel";

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("CopilotPanel", () => {
  beforeEach(() => {
    useStore.setState(useStore.getInitialState(), true);
    mockStartSSE.mockClear();
    mockStopSSE.mockClear();
  });

  it("renders without crashing", () => {
    render(<CopilotPanel />);
    expect(screen.getByText("Copilot")).toBeInTheDocument();
  });

  it("shows textarea placeholder when no session", () => {
    render(<CopilotPanel />);
    const ta = screen.getByPlaceholderText(/open a session to use copilot/i);
    expect(ta).toBeInTheDocument();
    expect(ta).toBeDisabled();
  });

  it("enables input when session is active", () => {
    useStore.setState({
      session: {
        id: "sess-1",
        name: "Test",
        status: "active",
        canvas_state: {
          schema_version: 1,
          nodes: [],
          edges: [],
          viewport: { zoom: 1, pan: { x: 0, y: 0 } },
          filters: { hidden_labels: [], hidden_types: [] },
        },
        config: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
    render(<CopilotPanel />);
    const ta = screen.getByPlaceholderText(/ask about the graph/i);
    expect(ta).not.toBeDisabled();
  });

  it("shows empty state message when no messages", () => {
    render(<CopilotPanel />);
    expect(
      screen.getByText(/ask copilot a question/i),
    ).toBeInTheDocument();
  });

  it("displays messages from the store", () => {
    useStore.setState({
      messages: [
        {
          id: "m1",
          session_id: "sess-1",
          role: "user",
          content: "Who knows Alice?",
          timestamp: new Date().toISOString(),
        },
        {
          id: "m2",
          session_id: "sess-1",
          role: "assistant",
          content: "Bob knows Alice.",
          timestamp: new Date().toISOString(),
        },
      ],
    });
    render(<CopilotPanel />);
    expect(screen.getByText("Who knows Alice?")).toBeInTheDocument();
    expect(screen.getByText("Bob knows Alice.")).toBeInTheDocument();
  });

  it("shows streaming bubble when isStreaming", () => {
    useStore.setState({ isStreaming: true, streamingContent: "Thinking…" });
    render(<CopilotPanel />);
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("send button is disabled when textarea is empty", () => {
    useStore.setState({
      session: {
        id: "sess-1",
        name: "Test",
        status: "active",
        canvas_state: {
          schema_version: 1,
          nodes: [],
          edges: [],
          viewport: { zoom: 1, pan: { x: 0, y: 0 } },
          filters: { hidden_labels: [], hidden_types: [] },
        },
        config: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
    render(<CopilotPanel />);
    const sendBtn = screen.getByRole("button", { name: /send/i });
    expect(sendBtn).toBeDisabled();
  });

  it("submitting a query calls useSSE.start and adds a user message", async () => {
    useStore.setState({
      session: {
        id: "sess-1",
        name: "Test",
        status: "active",
        canvas_state: {
          schema_version: 1,
          nodes: [],
          edges: [],
          viewport: { zoom: 1, pan: { x: 0, y: 0 } },
          filters: { hidden_labels: [], hidden_types: [] },
        },
        config: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });

    render(<CopilotPanel />);

    const ta = screen.getByPlaceholderText(/ask about the graph/i);
    fireEvent.change(ta, { target: { value: "Who is Alice?" } });

    const sendBtn = screen.getByRole("button", { name: /send/i });
    fireEvent.click(sendBtn);

    // User message should be added to store immediately
    await vi.waitFor(() => {
      const messages = useStore.getState().messages;
      expect(messages.some((m) => m.content === "Who is Alice?")).toBe(true);
    });

    // SSE stream should have been started
    expect(mockStartSSE).toHaveBeenCalledOnce();
    expect(mockStartSSE.mock.calls[0][0]).toContain("/copilot/query");
  });

  it("shows Stop button when streaming", () => {
    useStore.setState({ isStreaming: true, streamingContent: "" });
    render(<CopilotPanel />);
    expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
  });
});
