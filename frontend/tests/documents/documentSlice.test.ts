import { beforeEach, describe, expect, it } from "vitest";
import { createStore } from "zustand/vanilla";
import { createDocumentSlice, type DocumentSlice } from "@/store/documentSlice";
import type { DocumentLibrary } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeLibrary(id: string, name = "Test Library"): DocumentLibrary {
  return {
    id,
    name,
    created_at: new Date().toISOString(),
    doc_count: 0,
    chunk_count: 0,
    parse_quality: null,
    indexed_at: null,
  };
}

// ─── documentSlice ────────────────────────────────────────────────────────────

describe("documentSlice", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let store: ReturnType<typeof createStore<DocumentSlice>>;

  beforeEach(() => {
    store = createStore<DocumentSlice>()((...a: any[]) => createDocumentSlice(...a));
  });

  it("initial state has empty libraries and no attached library", () => {
    const state = store.getState();
    expect(state.libraries).toEqual([]);
    expect(state.attachedLibraryId).toBeNull();
    expect(state.isUploading).toBe(false);
    expect(state.uploadProgress).toBe(0);
  });

  it("loadLibraries replaces all libraries", () => {
    store.getState().addLibrary(makeLibrary("old"));
    store.getState().loadLibraries([makeLibrary("a"), makeLibrary("b")]);
    const ids = store.getState().libraries.map((l) => l.id);
    expect(ids).toEqual(["a", "b"]);
  });

  it("addLibrary appends to list", () => {
    store.getState().addLibrary(makeLibrary("x"));
    store.getState().addLibrary(makeLibrary("y"));
    expect(store.getState().libraries).toHaveLength(2);
    expect(store.getState().libraries[1].id).toBe("y");
  });

  it("removeLibrary removes by id", () => {
    store.getState().loadLibraries([makeLibrary("a"), makeLibrary("b"), makeLibrary("c")]);
    store.getState().removeLibrary("b");
    const ids = store.getState().libraries.map((l) => l.id);
    expect(ids).toEqual(["a", "c"]);
  });

  it("removeLibrary clears attachedLibraryId when it matches", () => {
    store.getState().addLibrary(makeLibrary("lib-1"));
    store.getState().setAttachedLibrary("lib-1");
    expect(store.getState().attachedLibraryId).toBe("lib-1");

    store.getState().removeLibrary("lib-1");
    expect(store.getState().attachedLibraryId).toBeNull();
  });

  it("removeLibrary keeps attachedLibraryId when a different library is removed", () => {
    store.getState().loadLibraries([makeLibrary("a"), makeLibrary("b")]);
    store.getState().setAttachedLibrary("b");

    store.getState().removeLibrary("a");
    expect(store.getState().attachedLibraryId).toBe("b");
    expect(store.getState().libraries).toHaveLength(1);
  });

  it("setAttachedLibrary sets id", () => {
    store.getState().setAttachedLibrary("lib-x");
    expect(store.getState().attachedLibraryId).toBe("lib-x");
  });

  it("clearAttachedLibrary nullifies id", () => {
    store.getState().setAttachedLibrary("lib-x");
    store.getState().clearAttachedLibrary();
    expect(store.getState().attachedLibraryId).toBeNull();
  });

  it("startUpload sets isUploading and resets progress", () => {
    store.getState().startUpload();
    expect(store.getState().isUploading).toBe(true);
    expect(store.getState().uploadProgress).toBe(0);
  });

  it("finishUpload clears isUploading and sets progress to 100", () => {
    store.getState().startUpload();
    store.getState().finishUpload();
    expect(store.getState().isUploading).toBe(false);
    expect(store.getState().uploadProgress).toBe(100);
  });
});
