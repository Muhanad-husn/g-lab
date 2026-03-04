import { API_BASE } from "@/lib/constants";
import type { CopilotMessage, CopilotQueryRequest } from "@/lib/types";
import { get } from "./client";

/**
 * Submit a copilot query and return the raw Response for SSE streaming.
 * The caller is responsible for reading the response body as a stream.
 */
export async function streamQuery(
  request: CopilotQueryRequest,
): Promise<Response> {
  const url = `${API_BASE}/copilot/query`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Copilot query failed: ${response.status} ${text}`);
  }

  return response;
}

/** Retrieve conversation history for a session. */
export async function getHistory(
  sessionId: string,
): Promise<CopilotMessage[]> {
  const { data } = await get<CopilotMessage[]>(
    `/copilot/history/${sessionId}`,
  );
  return data;
}
