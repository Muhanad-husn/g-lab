import * as client from "./client";
import type {
  ExpandRequest,
  ExpandResponse,
  PathRequest,
  PathResponse,
  RawQueryRequest,
  SchemaResponse,
  SearchRequest,
  SearchResponse,
} from "@/lib/types";

const BASE = "/graph";

export async function getSchema(): Promise<SchemaResponse> {
  const { data } = await client.get<SchemaResponse>(`${BASE}/schema`);
  return data;
}

export async function getSamples(
  label: string,
): Promise<Record<string, unknown>[]> {
  const { data } = await client.get<Record<string, unknown>[]>(
    `${BASE}/schema/samples/${encodeURIComponent(label)}`,
  );
  return data;
}

export async function getRelSamples(
  type: string,
): Promise<Record<string, unknown>[]> {
  const { data } = await client.get<Record<string, unknown>[]>(
    `${BASE}/schema/samples/rel/${encodeURIComponent(type)}`,
  );
  return data;
}

export async function search(body: SearchRequest): Promise<SearchResponse> {
  const { data } = await client.post<SearchResponse>(`${BASE}/search`, body);
  return data;
}

export async function expand(
  body: ExpandRequest,
): Promise<{ data: ExpandResponse; warnings: string[] }> {
  return client.post<ExpandResponse>(`${BASE}/expand`, body);
}

export async function findPaths(
  body: PathRequest,
): Promise<{ data: PathResponse; warnings: string[] }> {
  return client.post<PathResponse>(`${BASE}/paths`, body);
}

export async function rawQuery(
  body: RawQueryRequest,
): Promise<{ results: Record<string, unknown>[] }> {
  const { data } = await client.post<{ results: Record<string, unknown>[] }>(
    `${BASE}/query`,
    body,
  );
  return data;
}
