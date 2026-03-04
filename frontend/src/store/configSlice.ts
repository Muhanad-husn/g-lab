import type { StateCreator } from "zustand";
import {
  DEFAULT_PRESET,
  PRESETS,
  type LocalPreset,
  type PresetName,
} from "@/lib/constants";
import type { PresetResponse } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ConfigSlice {
  activePreset: PresetName;
  /** Resolved local preset option (hops, expansion limit defaults). */
  presetConfig: LocalPreset;

  // Phase 2 additions
  advancedMode: boolean;
  modelAssignments: {
    router: string;
    graphRetrieval: string;
    synthesiser: string;
  };
  /** Backend presets loaded from API. */
  presets: PresetResponse[];

  setPreset: (name: PresetName) => void;
  setAdvancedMode: (enabled: boolean) => void;
  setModelAssignments: (
    assignments: Partial<ConfigSlice["modelAssignments"]>,
  ) => void;
  /** Replace the full preset list (called after API load). */
  setPresets: (presets: PresetResponse[]) => void;
  /** Add or update a preset in the list. */
  upsertPreset: (preset: PresetResponse) => void;
  /** Remove a preset by id. */
  removePreset: (id: string) => void;
}

// ─── Defaults ─────────────────────────────────────────────────────────────────

const DEFAULT_MODEL_ASSIGNMENTS = {
  router: "anthropic/claude-3-haiku-20240307",
  graphRetrieval: "anthropic/claude-3-5-sonnet-20241022",
  synthesiser: "anthropic/claude-sonnet-4-20250514",
};

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createConfigSlice: StateCreator<
  ConfigSlice,
  [],
  [],
  ConfigSlice
> = (set) => ({
  activePreset: DEFAULT_PRESET,
  presetConfig: PRESETS[DEFAULT_PRESET],
  advancedMode: false,
  modelAssignments: DEFAULT_MODEL_ASSIGNMENTS,
  presets: [],

  setPreset: (name) =>
    set({
      activePreset: name,
      presetConfig: PRESETS[name],
    }),

  setAdvancedMode: (enabled) => set({ advancedMode: enabled }),

  setModelAssignments: (assignments) =>
    set((state) => ({
      modelAssignments: { ...state.modelAssignments, ...assignments },
    })),

  setPresets: (presets) => set({ presets }),

  upsertPreset: (preset) =>
    set((state) => {
      const idx = state.presets.findIndex((p) => p.id === preset.id);
      if (idx === -1) {
        return { presets: [...state.presets, preset] };
      }
      const updated = [...state.presets];
      updated[idx] = preset;
      return { presets: updated };
    }),

  removePreset: (id) =>
    set((state) => ({
      presets: state.presets.filter((p) => p.id !== id),
    })),
});
