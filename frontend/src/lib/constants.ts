// Hard limits — mirror of docs/ARCHITECTURE.md guardrail table
export const HARD_LIMITS = {
  MAX_CANVAS_NODES: 500,
  MAX_HOPS: 5,
  MAX_NODES_PER_EXPANSION: 100,
  CYPHER_TIMEOUT_MS: 30_000,
  COPILOT_TIMEOUT_MS: 120_000,
} as const;

// Canvas warning thresholds (for CanvasBanners in Stage 6)
export const CANVAS_WARN_AT = 400;
export const CANVAS_ERROR_AT = 500;

// Investigation presets — Phase 1 uses Standard only
export type PresetName = "standard" | "deep_dive" | "quick_look";

export interface PresetConfig {
  name: PresetName;
  label: string;
  default_hops: number;
  default_expansion_limit: number;
}

export const PRESETS: Record<PresetName, PresetConfig> = {
  standard: {
    name: "standard",
    label: "Standard Investigation",
    default_hops: 2,
    default_expansion_limit: 25,
  },
  deep_dive: {
    name: "deep_dive",
    label: "Deep Dive",
    default_hops: 3,
    default_expansion_limit: 50,
  },
  quick_look: {
    name: "quick_look",
    label: "Quick Look",
    default_hops: 1,
    default_expansion_limit: 10,
  },
};

export const DEFAULT_PRESET: PresetName = "standard";

// API base URL — resolved via Vite proxy in dev, same-origin in production
export const API_BASE = "/api/v1";
