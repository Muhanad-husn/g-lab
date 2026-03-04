import type { StateCreator } from "zustand";
import {
  DEFAULT_PRESET,
  PRESETS,
  type PresetConfig,
  type PresetName,
} from "@/lib/constants";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ConfigSlice {
  activePreset: PresetName;
  /** Resolved config for the active preset (hops, expansion limit, etc.). */
  presetConfig: PresetConfig;

  setPreset: (name: PresetName) => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createConfigSlice: StateCreator<
  ConfigSlice,
  [],
  [],
  ConfigSlice
> = (set) => ({
  activePreset: DEFAULT_PRESET,
  presetConfig: PRESETS[DEFAULT_PRESET],

  setPreset: (name) =>
    set({
      activePreset: name,
      presetConfig: PRESETS[name],
    }),
});
