import type { StateCreator } from "zustand";
import type { DocumentLibrary } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DocumentSlice {
  libraries: DocumentLibrary[];
  attachedLibraryId: string | null;
  isUploading: boolean;
  uploadProgress: number; // 0–100

  loadLibraries: (libraries: DocumentLibrary[]) => void;
  addLibrary: (library: DocumentLibrary) => void;
  removeLibrary: (id: string) => void;
  setAttachedLibrary: (id: string) => void;
  clearAttachedLibrary: () => void;
  startUpload: () => void;
  finishUpload: () => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createDocumentSlice: StateCreator<
  DocumentSlice,
  [],
  [],
  DocumentSlice
> = (set) => ({
  libraries: [],
  attachedLibraryId: null,
  isUploading: false,
  uploadProgress: 0,

  loadLibraries: (libraries) => set({ libraries }),

  addLibrary: (library) =>
    set((state) => ({ libraries: [...state.libraries, library] })),

  removeLibrary: (id) =>
    set((state) => ({
      libraries: state.libraries.filter((lib) => lib.id !== id),
      attachedLibraryId: state.attachedLibraryId === id ? null : state.attachedLibraryId,
    })),

  setAttachedLibrary: (id) => set({ attachedLibraryId: id }),

  clearAttachedLibrary: () => set({ attachedLibraryId: null }),

  startUpload: () => set({ isUploading: true, uploadProgress: 0 }),

  finishUpload: () => set({ isUploading: false, uploadProgress: 100 }),
});
