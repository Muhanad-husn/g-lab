import type { StateCreator } from "zustand";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Banner {
  id: string;
  level: "warning" | "error";
  message: string;
}

export interface PanelStates {
  navigatorCollapsed: boolean;
  inspectorCollapsed: boolean;
}

export interface UiSlice {
  /** IDs of selected nodes/edges in Cytoscape. */
  selectedIds: string[];
  panelStates: PanelStates;
  /** Dismissible in-canvas banners (e.g., guardrail warnings). */
  banners: Banner[];

  setSelectedIds: (ids: string[]) => void;
  clearSelection: () => void;
  setPanelState: (panel: keyof PanelStates, value: boolean) => void;
  pushBanner: (banner: Omit<Banner, "id">) => string;
  dismissBanner: (id: string) => void;
  clearBanners: () => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _bannerCounter = 0;
function bannerId(): string {
  _bannerCounter += 1;
  return `banner-${Date.now()}-${_bannerCounter}`;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createUiSlice: StateCreator<UiSlice, [], [], UiSlice> = (set) => ({
  selectedIds: [],
  panelStates: { navigatorCollapsed: false, inspectorCollapsed: false },
  banners: [],

  setSelectedIds: (ids) => set({ selectedIds: ids }),

  clearSelection: () => set({ selectedIds: [] }),

  setPanelState: (panel, value) =>
    set((state) => ({
      panelStates: { ...state.panelStates, [panel]: value },
    })),

  pushBanner: (banner) => {
    const id = bannerId();
    set((state) => ({ banners: [...state.banners, { ...banner, id }] }));
    return id;
  },

  dismissBanner: (id) =>
    set((state) => ({
      banners: state.banners.filter((b) => b.id !== id),
    })),

  clearBanners: () => set({ banners: [] }),
});
