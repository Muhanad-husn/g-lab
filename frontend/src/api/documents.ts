import { API_BASE } from "@/lib/constants";
import type { ApiError, ApiResponse } from "@/lib/types";
import type {
  DocumentLibrary,
  DocumentUploadResponse,
  LibraryAttachRequest,
} from "@/lib/types";
import { ApiRequestError } from "./client";
import { del, get, post } from "./client";

export async function listLibraries(): Promise<DocumentLibrary[]> {
  const { data } = await get<DocumentLibrary[]>("/documents/libraries");
  return data;
}

export async function createLibrary(name: string): Promise<DocumentLibrary> {
  const { data } = await post<DocumentLibrary>("/documents/libraries", { name });
  return data;
}

export async function deleteLibrary(id: string): Promise<void> {
  await del<null>(`/documents/libraries/${id}`);
}

/** Upload one or more files to a library. Uses multipart FormData (not JSON). */
export async function uploadDocuments(
  libraryId: string,
  files: File[],
): Promise<DocumentUploadResponse[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const url = `${API_BASE}/documents/libraries/${libraryId}/upload`;
  const response = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: formData,
  });

  const json = (await response.json()) as
    | ApiResponse<DocumentUploadResponse[]>
    | ApiError;

  if (!response.ok) {
    throw new ApiRequestError(response.status, json as ApiError);
  }

  return (json as ApiResponse<DocumentUploadResponse[]>).data;
}

export async function removeDocument(
  libraryId: string,
  docId: string,
): Promise<void> {
  await del<null>(`/documents/libraries/${libraryId}/docs/${docId}`);
}

export async function attachLibrary(
  libraryId: string,
  sessionId: string,
): Promise<void> {
  const body: LibraryAttachRequest = { session_id: sessionId };
  await post<null>(`/documents/libraries/${libraryId}/attach`, body);
}

export async function detachLibrary(sessionId: string): Promise<void> {
  const body: LibraryAttachRequest = { session_id: sessionId };
  await post<null>("/documents/libraries/detach", body);
}

export async function getAttachedLibrary(
  sessionId: string,
): Promise<string | null> {
  const { data } = await get<{ library_id: string | null }>(
    `/documents/libraries/attached/${sessionId}`,
  );
  return data.library_id;
}
