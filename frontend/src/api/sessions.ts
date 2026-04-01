import * as client from "./client";
import { API_BASE } from "@/lib/constants";
import type {
  SessionCreate,
  SessionResponse,
  SessionUpdate,
} from "@/lib/types";

const BASE = "/sessions";

/** Returns all sessions, sorted by updated_at descending. */
export async function listSessions(): Promise<SessionResponse[]> {
  const { data } = await client.get<SessionResponse[]>(BASE);
  return data;
}

export async function createSession(
  body: SessionCreate,
): Promise<SessionResponse> {
  const { data } = await client.post<SessionResponse>(BASE, body);
  return data;
}

export async function getSession(id: string): Promise<SessionResponse> {
  const { data } = await client.get<SessionResponse>(`${BASE}/${id}`);
  return data;
}

/** Returns null if no active session exists (404). */
export async function getLastActive(): Promise<SessionResponse | null> {
  try {
    const { data } = await client.get<SessionResponse>(`${BASE}/last-active`);
    return data;
  } catch {
    return null;
  }
}

export async function updateSession(
  id: string,
  body: SessionUpdate,
): Promise<SessionResponse> {
  const { data } = await client.put<SessionResponse>(`${BASE}/${id}`, body);
  return data;
}

export async function deleteSession(id: string): Promise<void> {
  await client.del<void>(`${BASE}/${id}`);
}

export async function resetSession(id: string): Promise<SessionResponse> {
  const { data } = await client.post<SessionResponse>(
    `${BASE}/${id}/reset`,
  );
  return data;
}

/**
 * Exports a session as a .g-lab-session ZIP archive.
 * Uses raw fetch because the response is binary, not JSON.
 */
export async function exportSession(id: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}${BASE}/${id}/export`, {
    method: "POST",
  });
  if (!res.ok) {
    const json = (await res.json().catch(() => ({}))) as {
      error?: { message?: string };
    };
    throw new Error(json?.error?.message ?? "Export failed");
  }
  return res.blob();
}

/**
 * Imports a .g-lab-session ZIP file and returns the created session.
 * Uses raw fetch with FormData because the request body is a file upload.
 */
export async function importSession(file: File): Promise<SessionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}${BASE}/import`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const json = (await res.json().catch(() => ({}))) as {
      error?: { message?: string };
    };
    throw new Error(json?.error?.message ?? "Import failed");
  }
  const json = (await res.json()) as { data: SessionResponse };
  return json.data;
}
