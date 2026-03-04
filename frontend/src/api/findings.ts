import * as client from "./client";
import type {
  FindingCreate,
  FindingResponse,
  FindingUpdate,
} from "@/lib/types";

function base(sessionId: string): string {
  return `/sessions/${sessionId}/findings`;
}

export async function listFindings(
  sessionId: string,
): Promise<FindingResponse[]> {
  const { data } = await client.get<FindingResponse[]>(base(sessionId));
  return data;
}

export async function createFinding(
  sessionId: string,
  body: FindingCreate,
): Promise<FindingResponse> {
  const { data } = await client.post<FindingResponse>(base(sessionId), body);
  return data;
}

export async function updateFinding(
  sessionId: string,
  findingId: string,
  body: FindingUpdate,
): Promise<FindingResponse> {
  const { data } = await client.put<FindingResponse>(
    `${base(sessionId)}/${findingId}`,
    body,
  );
  return data;
}

export async function deleteFinding(
  sessionId: string,
  findingId: string,
): Promise<void> {
  await client.del<void>(`${base(sessionId)}/${findingId}`);
}
