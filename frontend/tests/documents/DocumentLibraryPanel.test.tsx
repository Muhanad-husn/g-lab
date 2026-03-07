// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useStore } from "@/store";
import type { DocumentLibrary } from "@/lib/types";

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockCreateLibrary = vi.fn().mockResolvedValue(true);
const mockDeleteLibrary = vi.fn().mockResolvedValue(true);
const mockAttachLibrary = vi.fn().mockResolvedValue(true);
const mockDetachLibrary = vi.fn().mockResolvedValue(true);

vi.mock("@/hooks/useDocumentActions", () => ({
  useDocumentActions: () => ({
    createLibrary: mockCreateLibrary,
    deleteLibrary: mockDeleteLibrary,
    attachLibrary: mockAttachLibrary,
    detachLibrary: mockDetachLibrary,
    fetchLibraries: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue([]),
    uploadFiles: vi.fn(),
    removeDocument: vi.fn(),
    ingestDocument: vi.fn(),
  }),
}));

vi.mock("@/components/documents/DocumentUpload", () => ({
  DocumentUpload: ({ libraryId }: { libraryId: string }) => (
    <div data-testid={`upload-${libraryId}`} />
  ),
}));

// Import after mocks
import { DocumentLibraryPanel } from "@/components/documents/DocumentLibraryPanel";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeLibrary(overrides?: Partial<DocumentLibrary>): DocumentLibrary {
  return {
    id: "lib-1",
    name: "Test Library",
    created_at: new Date().toISOString(),
    doc_count: 0,
    chunk_count: 0,
    parse_quality: null,
    indexed_at: null,
    ...overrides,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("DocumentLibraryPanel", () => {
  beforeEach(() => {
    useStore.setState(useStore.getInitialState(), true);
    mockCreateLibrary.mockClear();
    mockDeleteLibrary.mockClear();
    mockAttachLibrary.mockClear();
    mockDetachLibrary.mockClear();
  });

  it("renders empty state when no libraries", () => {
    render(<DocumentLibraryPanel />);
    expect(screen.getByText(/no document libraries yet/i)).toBeInTheDocument();
    expect(screen.getByText(/0 libraries/i)).toBeInTheDocument();
  });

  it("shows singular library count in header", () => {
    useStore.setState({ libraries: [makeLibrary()] });
    render(<DocumentLibraryPanel />);
    expect(screen.getByText(/1 library/i)).toBeInTheDocument();
  });

  it("shows plural library count in header", () => {
    useStore.setState({
      libraries: [makeLibrary({ id: "a" }), makeLibrary({ id: "b" })],
    });
    render(<DocumentLibraryPanel />);
    expect(screen.getByText(/2 libraries/i)).toBeInTheDocument();
  });

  it("renders library name and doc count", () => {
    useStore.setState({
      libraries: [makeLibrary({ name: "My Docs", doc_count: 3, chunk_count: 42 })],
    });
    render(<DocumentLibraryPanel />);
    expect(screen.getByText("My Docs")).toBeInTheDocument();
    expect(screen.getByText(/3 docs/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });

  it("shows create form when New button clicked", () => {
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByTitle("New library"));
    expect(screen.getByPlaceholderText(/library name/i)).toBeInTheDocument();
  });

  it("hides create form when Cancel clicked", () => {
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByTitle("New library"));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByPlaceholderText(/library name/i)).not.toBeInTheDocument();
  });

  it("shows delete confirmation on trash click", () => {
    useStore.setState({ libraries: [makeLibrary({ name: "My Docs" })] });
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByLabelText("Delete library"));
    expect(screen.getByText(/permanently remove/i)).toBeInTheDocument();
    expect(screen.getByText(/"My Docs"/)).toBeInTheDocument();
  });

  it("cancels delete confirmation", () => {
    useStore.setState({ libraries: [makeLibrary({ name: "My Docs" })] });
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByLabelText("Delete library"));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText(/permanently remove/i)).not.toBeInTheDocument();
  });

  it("shows attached badge when library is attached", () => {
    useStore.setState({
      libraries: [makeLibrary({ id: "lib-1" })],
      attachedLibraryId: "lib-1",
    });
    render(<DocumentLibraryPanel />);
    expect(screen.getByText("attached")).toBeInTheDocument();
  });

  it("calls attachLibrary when attach button clicked", () => {
    useStore.setState({
      libraries: [makeLibrary({ id: "lib-1" })],
      attachedLibraryId: null,
    });
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByLabelText("Attach library"));
    expect(mockAttachLibrary).toHaveBeenCalledWith("lib-1");
  });

  it("calls detachLibrary when detach button clicked", () => {
    useStore.setState({
      libraries: [makeLibrary({ id: "lib-1" })],
      attachedLibraryId: "lib-1",
    });
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByLabelText("Detach library"));
    expect(mockDetachLibrary).toHaveBeenCalled();
  });

  it("expands library to show upload area on row click", () => {
    useStore.setState({ libraries: [makeLibrary({ id: "lib-1" })] });
    render(<DocumentLibraryPanel />);
    fireEvent.click(screen.getByLabelText("Expand"));
    expect(screen.getByTestId("upload-lib-1")).toBeInTheDocument();
  });
});
