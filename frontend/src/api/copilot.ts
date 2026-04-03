import { API_BASE } from "@/lib/constants";
import type {
  ConversationSummary,
  CopilotMessage,
  CopilotQueryRequest,
} from "@/lib/types";
import { del, get, post } from "./client";

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

/** Retrieve conversation history for a session (optionally for a specific conversation). */
export async function getHistory(
  sessionId: string,
  conversationId?: string,
): Promise<CopilotMessage[]> {
  const params = conversationId
    ? `?conversation_id=${encodeURIComponent(conversationId)}`
    : "";
  const { data } = await get<CopilotMessage[]>(
    `/copilot/history/${sessionId}${params}`,
  );
  return data;
}

/** Clear all conversation history for a session. */
export async function clearHistory(
  sessionId: string,
): Promise<{ deleted: number }> {
  const { data } = await del<{ deleted: number }>(
    `/copilot/history/${sessionId}`,
  );
  return data;
}

/** List all conversations for a session, newest first. */
export async function listConversations(
  sessionId: string,
): Promise<ConversationSummary[]> {
  const { data } = await get<ConversationSummary[]>(
    `/copilot/conversations/${sessionId}`,
  );
  return data;
}

/** Start a new conversation for a session. Returns the new conversation ID. */
export async function startNewConversation(
  sessionId: string,
): Promise<string> {
  const { data } = await post<{ conversation_id: string }>(
    `/copilot/conversations/${sessionId}/new`,
  );
  return data.conversation_id;
}
