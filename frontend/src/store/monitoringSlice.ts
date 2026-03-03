/**
 * Monitoring store slice — toasts, active operations, Neo4j status, dev logs.
 *
 * Integrates with the API client (auto-toast on warnings/errors) and
 * useHealthPolling (Neo4j connection status).
 */
import type { StateCreator } from "zustand";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastLevel = "info" | "warning" | "error" | "success";

export interface Toast {
  id: string;
  level: ToastLevel;
  title: string;
  message?: string;
  /** Auto-dismiss after this many ms. 0 = sticky. Default 5000. */
  duration: number;
  timestamp: number;
}

export interface ActiveOperation {
  id: string;
  type: string;
  label: string;
  startedAt: number;
}

export type Neo4jConnectionStatus =
  | "connected"
  | "degraded"
  | "disconnected"
  | "unknown";

export interface DevLogEntry {
  id: string;
  timestamp: number;
  method: string;
  path: string;
  status: number;
  duration_ms: number;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Slice interface
// ---------------------------------------------------------------------------

export interface MonitoringSlice {
  // Toasts — transient notifications
  toasts: Toast[];
  addToast: (
    t: Omit<Toast, "id" | "timestamp"> & { duration?: number },
  ) => string;
  dismissToast: (id: string) => void;

  // Active operations — loading state tracking
  activeOperations: ActiveOperation[];
  startOperation: (type: string, label: string) => string;
  endOperation: (id: string) => void;

  // Neo4j connection status
  neo4jStatus: Neo4jConnectionStatus;
  setNeo4jStatus: (status: Neo4jConnectionStatus) => void;

  // Dev panel (dev mode only)
  devLogs: DevLogEntry[];
  addDevLog: (entry: Omit<DevLogEntry, "id" | "timestamp">) => void;
  isDevPanelOpen: boolean;
  toggleDevPanel: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _counter = 0;
function uid(): string {
  _counter += 1;
  return `${Date.now()}-${_counter}`;
}

const DEV_LOG_CAP = 200;

// ---------------------------------------------------------------------------
// Slice creator
// ---------------------------------------------------------------------------

export const createMonitoringSlice: StateCreator<
  MonitoringSlice,
  [],
  [],
  MonitoringSlice
> = (set) => ({
  // -- Toasts ---------------------------------------------------------------
  toasts: [],

  addToast: (t) => {
    const id = uid();
    const toast: Toast = {
      ...t,
      id,
      duration: t.duration ?? 5000,
      timestamp: Date.now(),
    };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    return id;
  },

  dismissToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  // -- Active operations ----------------------------------------------------
  activeOperations: [],

  startOperation: (type, label) => {
    const id = uid();
    const op: ActiveOperation = { id, type, label, startedAt: Date.now() };
    set((state) => ({
      activeOperations: [...state.activeOperations, op],
    }));
    return id;
  },

  endOperation: (id) => {
    set((state) => ({
      activeOperations: state.activeOperations.filter((op) => op.id !== id),
    }));
  },

  // -- Neo4j status ---------------------------------------------------------
  neo4jStatus: "unknown",

  setNeo4jStatus: (status) => {
    set({ neo4jStatus: status });
  },

  // -- Dev panel ------------------------------------------------------------
  devLogs: [],

  addDevLog: (entry) => {
    const full: DevLogEntry = { ...entry, id: uid(), timestamp: Date.now() };
    set((state) => ({
      devLogs: [...state.devLogs, full].slice(-DEV_LOG_CAP),
    }));
  },

  isDevPanelOpen: false,

  toggleDevPanel: () => {
    set((state) => ({ isDevPanelOpen: !state.isDevPanelOpen }));
  },
});
