import type { StateCreator } from "zustand";
import type { FindingResponse, SessionResponse } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SessionSlice {
  session: SessionResponse | null;
  findings: FindingResponse[];

  setSession: (session: SessionResponse | null) => void;
  clearSession: () => void;
  setFindings: (findings: FindingResponse[]) => void;
  addFinding: (finding: FindingResponse) => void;
  updateFinding: (finding: FindingResponse) => void;
  removeFinding: (id: string) => void;
}

// ─── Slice creator ────────────────────────────────────────────────────────────

export const createSessionSlice: StateCreator<
  SessionSlice,
  [],
  [],
  SessionSlice
> = (set) => ({
  session: null,
  findings: [],

  setSession: (session) => set({ session }),

  clearSession: () => set({ session: null, findings: [] }),

  setFindings: (findings) => set({ findings }),

  addFinding: (finding) =>
    set((state) => ({ findings: [...state.findings, finding] })),

  updateFinding: (finding) =>
    set((state) => ({
      findings: state.findings.map((f) => (f.id === finding.id ? finding : f)),
    })),

  removeFinding: (id) =>
    set((state) => ({
      findings: state.findings.filter((f) => f.id !== id),
    })),
});
