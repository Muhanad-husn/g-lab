import { create } from "zustand";
import { createConfigSlice, type ConfigSlice } from "./configSlice";
import { createGraphSlice, type GraphSlice } from "./graphSlice";
import { createMonitoringSlice, type MonitoringSlice } from "./monitoringSlice";
import { createSessionSlice, type SessionSlice } from "./sessionSlice";
import { createUiSlice, type UiSlice } from "./uiSlice";

// ─── Combined store type ───────────────────────────────────────────────────────

export type AllSlices = GraphSlice &
  SessionSlice &
  UiSlice &
  ConfigSlice &
  MonitoringSlice;

// ─── Bound store ───────────────────────────────────────────────────────────────

export const useStore = create<AllSlices>()((...a) => ({
  ...createGraphSlice(...a),
  ...createSessionSlice(...a),
  ...createUiSlice(...a),
  ...createConfigSlice(...a),
  ...createMonitoringSlice(...a),
}));
