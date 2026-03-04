import { API_BASE } from "@/lib/constants";
import type { ApiError, ApiResponse } from "@/lib/types";

// ─── Typed error ──────────────────────────────────────────────────────────────

export class ApiRequestError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: Record<string, unknown>;

  constructor(status: number, apiError: ApiError) {
    super(apiError.error.message);
    this.name = "ApiRequestError";
    this.code = apiError.error.code;
    this.status = status;
    this.detail = apiError.error.detail;
  }
}

// ─── Internal fetch helper ───────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<{ data: T; warnings: string[] }> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const json = (await response.json()) as ApiResponse<T> | ApiError;

  if (!response.ok) {
    throw new ApiRequestError(response.status, json as ApiError);
  }

  const envelope = json as ApiResponse<T>;
  return { data: envelope.data, warnings: envelope.warnings };
}

// ─── Public API ───────────────────────────────────────────────────────────────

export async function get<T>(
  path: string,
): Promise<{ data: T; warnings: string[] }> {
  return request<T>("GET", path);
}

export async function post<T>(
  path: string,
  body?: unknown,
): Promise<{ data: T; warnings: string[] }> {
  return request<T>("POST", path, body ?? null);
}

export async function put<T>(
  path: string,
  body?: unknown,
): Promise<{ data: T; warnings: string[] }> {
  return request<T>("PUT", path, body ?? null);
}

export async function del<T>(
  path: string,
): Promise<{ data: T; warnings: string[] }> {
  return request<T>("DELETE", path);
}
