import {
  attachLibrary,
  createLibrary,
  deleteLibrary,
  detachLibrary,
  listLibraries,
  removeDocument,
  uploadDocuments,
} from "@/api/documents";
import { useStore } from "@/store";
import { MAX_DOC_UPLOAD_SIZE_MB } from "@/lib/constants";
import type { DocumentUploadResponse } from "@/lib/types";

// ─── useDocumentActions ───────────────────────────────────────────────────────

/**
 * Bridge between the document library UI and the API + store.
 * All error paths push a banner via uiSlice.
 */
export function useDocumentActions() {
  const addLibrary = useStore((s) => s.addLibrary);
  const removeLibrary = useStore((s) => s.removeLibrary);
  const loadLibraries = useStore((s) => s.loadLibraries);
  const setAttachedLibrary = useStore((s) => s.setAttachedLibrary);
  const clearAttachedLibrary = useStore((s) => s.clearAttachedLibrary);
  const startUpload = useStore((s) => s.startUpload);
  const finishUpload = useStore((s) => s.finishUpload);
  const pushBanner = useStore((s) => s.pushBanner);
  const session = useStore((s) => s.session);

  function pushError(message: string) {
    pushBanner({ level: "error", message });
  }

  async function fetchLibraries() {
    try {
      const libs = await listLibraries();
      loadLibraries(libs);
    } catch {
      pushError("Failed to load document libraries.");
    }
  }

  async function handleCreateLibrary(name: string): Promise<boolean> {
    try {
      const lib = await createLibrary(name.trim());
      addLibrary(lib);
      return true;
    } catch {
      pushError(`Failed to create library "${name}".`);
      return false;
    }
  }

  async function handleDeleteLibrary(id: string): Promise<boolean> {
    try {
      await deleteLibrary(id);
      removeLibrary(id);
      return true;
    } catch {
      pushError("Failed to delete library.");
      return false;
    }
  }

  async function handleUploadFiles(
    libraryId: string,
    files: File[],
  ): Promise<DocumentUploadResponse[] | null> {
    const oversized = files.filter(
      (f) => f.size > MAX_DOC_UPLOAD_SIZE_MB * 1024 * 1024,
    );
    if (oversized.length > 0) {
      pushError(
        `${oversized[0].name} exceeds the ${MAX_DOC_UPLOAD_SIZE_MB} MB limit.`,
      );
      return null;
    }

    startUpload();
    try {
      const results = await uploadDocuments(libraryId, files);
      // Refresh library list to get updated counts
      await fetchLibraries();
      return results;
    } catch (err) {
      pushError(err instanceof Error ? err.message : "Upload failed.");
      return null;
    } finally {
      finishUpload();
    }
  }

  async function handleRemoveDocument(
    libraryId: string,
    docId: string,
  ): Promise<boolean> {
    try {
      await removeDocument(libraryId, docId);
      await fetchLibraries();
      return true;
    } catch {
      pushError("Failed to remove document.");
      return false;
    }
  }

  async function handleAttachLibrary(libraryId: string): Promise<boolean> {
    if (!session) {
      pushError("No active session to attach the library to.");
      return false;
    }
    try {
      await attachLibrary(libraryId, session.id);
      setAttachedLibrary(libraryId);
      return true;
    } catch {
      pushError("Failed to attach library to session.");
      return false;
    }
  }

  async function handleDetachLibrary(): Promise<boolean> {
    if (!session) {
      pushError("No active session to detach from.");
      return false;
    }
    try {
      await detachLibrary(session.id);
      clearAttachedLibrary();
      return true;
    } catch {
      pushError("Failed to detach library.");
      return false;
    }
  }

  return {
    fetchLibraries,
    createLibrary: handleCreateLibrary,
    deleteLibrary: handleDeleteLibrary,
    uploadFiles: handleUploadFiles,
    removeDocument: handleRemoveDocument,
    attachLibrary: handleAttachLibrary,
    detachLibrary: handleDetachLibrary,
  };
}
