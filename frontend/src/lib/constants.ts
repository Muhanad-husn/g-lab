// Hard limits — mirror of docs/ARCHITECTURE.md guardrail table
export const HARD_LIMITS = {
  MAX_CANVAS_NODES: 500,
  MAX_HOPS: 5,
  MAX_NODES_PER_EXPANSION: 100,
  CYPHER_TIMEOUT_MS: 30_000,
  COPILOT_TIMEOUT_MS: 300_000,
} as const;

// Canvas warning thresholds (for CanvasBanners in Stage 6)
export const CANVAS_WARN_AT = 400;
export const CANVAS_ERROR_AT = 500;

// Investigation presets — Phase 1 uses Standard only
export type PresetName = "standard" | "deep_dive" | "quick_look";

/** Frontend-only static preset option (not the API PresetConfig from types.ts). */
export interface LocalPreset {
  name: PresetName;
  label: string;
  default_hops: number;
  default_expansion_limit: number;
}

export const PRESETS: Record<PresetName, LocalPreset> = {
  standard: {
    name: "standard",
    label: "Standard Investigation",
    default_hops: 2,
    default_expansion_limit: 25,
  },
  deep_dive: {
    name: "deep_dive",
    label: "Deep Dive",
    default_hops: 5,
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

// ─── Phase 2: Copilot constants ───────────────────────────────────────────────

export const COPILOT_TIMEOUT_MS = 300_000;

export const CONFIDENCE_BANDS = {
  HIGH: { threshold: 0.7, label: "High", color: "green" },
  MEDIUM: { threshold: 0.4, label: "Medium", color: "yellow" },
  LOW: { threshold: 0, label: "Low", color: "red" },
} as const;

export const SSE_EVENT_TYPES = [
  "text_chunk",
  "evidence",
  "graph_delta",
  "confidence",
  "status",
  "done",
  "error",
] as const;

// ─── Phase 3: Document Library constants ──────────────────────────────────────

export const MAX_DOC_UPLOAD_SIZE_MB = 50;
export const MAX_DOCS_PER_LIBRARY = 100;

export const PARSE_QUALITY_TIERS = {
  high: { label: "High", description: "Structured extraction (Docling)" },
  standard: { label: "Standard", description: "General extraction (Unstructured)" },
  basic: { label: "Basic", description: "Raw text fallback" },
  pending: { label: "Pending", description: "Awaiting ingestion" },
} as const;
