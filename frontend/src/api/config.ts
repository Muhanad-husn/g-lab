import type {
  ModelInfo,
  PresetCreate,
  PresetResponse,
  PresetUpdate,
} from "@/lib/types";
import { del, get, post, put } from "./client";

export async function getPresets(): Promise<PresetResponse[]> {
  const { data } = await get<PresetResponse[]>("/config/presets");
  return data;
}

export async function createPreset(
  preset: PresetCreate,
): Promise<PresetResponse> {
  const { data } = await post<PresetResponse>("/config/presets", preset);
  return data;
}

export async function updatePreset(
  id: string,
  update: PresetUpdate,
): Promise<PresetResponse> {
  const { data } = await put<PresetResponse>(`/config/presets/${id}`, update);
  return data;
}

export async function deletePreset(id: string): Promise<void> {
  await del<null>(`/config/presets/${id}`);
}

export async function getModels(): Promise<ModelInfo[]> {
  const { data } = await get<ModelInfo[]>("/config/models");
  return data;
}
