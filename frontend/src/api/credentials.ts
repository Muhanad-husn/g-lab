import { get, post } from "./client";

export interface CredentialsStatus {
  neo4j_uri: string;
  neo4j_user: string;
  neo4j_password_set: boolean;
  openrouter_api_key_set: boolean;
  neo4j_connected: boolean;
  openrouter_configured: boolean;
}

export interface CredentialsUpdate {
  neo4j_uri?: string;
  neo4j_user?: string;
  neo4j_password?: string;
  openrouter_api_key?: string;
}

export async function getCredentials(): Promise<CredentialsStatus> {
  const { data } = await get<CredentialsStatus>("/config/credentials");
  return data;
}

export async function updateCredentials(
  update: CredentialsUpdate,
): Promise<CredentialsStatus> {
  const { data } = await post<CredentialsStatus>("/config/credentials", update);
  return data;
}
