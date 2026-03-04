import * as client from "./client";
import type {
  SessionCreate,
  SessionResponse,
  SessionUpdate,
} from "@/lib/types";

const BASE = "/sessions";

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
