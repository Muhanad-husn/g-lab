import { useRef, useState } from "react";
import { Download, Pencil, Settings, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { createSession, exportSession, importSession, updateSession } from "@/api/sessions";
import {
  createPreset,
  deletePreset,
} from "@/api/config";
import { useStore } from "@/store";
import { PRESETS, type PresetName } from "@/lib/constants";
import type { PresetConfig, PresetResponse } from "@/lib/types";

// ─── Neo4j status indicator ───────────────────────────────────────────────────

function StatusDot() {
  const status = useStore((s) => s.neo4jStatus);

  const color =
    status === "connected"
      ? "bg-green-500"
      : status === "degraded"
        ? "bg-yellow-500"
        : status === "disconnected"
          ? "bg-red-500"
          : "bg-muted-foreground";

  const label =
    status === "connected"
      ? "Neo4j connected"
      : status === "degraded"
        ? "Neo4j degraded"
        : status === "disconnected"
          ? "Neo4j disconnected"
          : "Neo4j status unknown";

  return (
    <span className="flex items-center gap-1.5" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="text-xs text-muted-foreground hidden sm:inline">
        {label}
      </span>
    </span>
  );
}

// ─── Vector store status indicator ───────────────────────────────────────────

function VectorStoreDot() {
  const status = useStore((s) => s.vectorStoreStatus);
  const attachedLibraryId = useStore((s) => s.attachedLibraryId);
  const libraries = useStore((s) => s.libraries);

  const attachedLibrary = attachedLibraryId
    ? libraries.find((l) => l.id === attachedLibraryId)
    : null;

  const color =
    status === "ready"
      ? "bg-violet-400"
      : status === "unconfigured"
        ? "bg-muted-foreground"
        : status === "degraded"
          ? "bg-red-500"
          : "bg-muted-foreground/50";

  const baseLabel =
    status === "ready"
      ? "Docs ready"
      : status === "unconfigured"
        ? "Docs unconfigured"
        : status === "degraded"
          ? "Docs degraded"
          : "Docs status unknown";

  const title = attachedLibrary
    ? `${baseLabel} — attached: ${attachedLibrary.name}`
    : baseLabel;

  return (
    <span className="flex items-center gap-1.5" title={title}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="text-xs text-muted-foreground hidden xl:inline truncate max-w-32">
        {attachedLibrary ? attachedLibrary.name : baseLabel}
      </span>
    </span>
  );
}

// ─── Copilot status indicator ─────────────────────────────────────────────────

function CopilotStatusDot() {
  const status = useStore((s) => s.copilotStatus);

  const color =
    status === "ready"
      ? "bg-blue-400"
      : status === "unconfigured"
        ? "bg-muted-foreground"
        : "bg-muted-foreground/50";

  const label =
    status === "ready"
      ? "Copilot ready"
      : status === "unconfigured"
        ? "Copilot unconfigured"
        : "Copilot status unknown";

  return (
    <span className="flex items-center gap-1.5" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="text-xs text-muted-foreground hidden lg:inline">
        {label}
      </span>
    </span>
  );
}

// ─── Preset selector ──────────────────────────────────────────────────────────

function PresetSelector() {
  const activePreset = useStore((s) => s.activePreset);
  const setPreset = useStore((s) => s.setPreset);

  return (
    <select
      value={activePreset}
      onChange={(e) => setPreset(e.target.value as PresetName)}
      className="h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
    >
      {Object.values(PRESETS).map((p) => (
        <option key={p.name} value={p.name}>
          {p.label}
        </option>
      ))}
    </select>
  );
}

// ─── Copilot settings dialog ──────────────────────────────────────────────────

interface CopilotSettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

function CopilotSettingsDialog({ open, onClose }: CopilotSettingsDialogProps) {
  const advancedMode = useStore((s) => s.advancedMode);
  const setAdvancedMode = useStore((s) => s.setAdvancedMode);
  const modelAssignments = useStore((s) => s.modelAssignments);
  const setModelAssignments = useStore((s) => s.setModelAssignments);

  const [router, setRouter] = useState(modelAssignments.router);
  const [graphRetrieval, setGraphRetrieval] = useState(modelAssignments.graphRetrieval);
  const [synthesiser, setSynthesiser] = useState(modelAssignments.synthesiser);

  function handleSave() {
    setModelAssignments({ router, graphRetrieval, synthesiser });
    onClose();
  }

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) {
      // Reset local state to current store values on cancel
      setRouter(modelAssignments.router);
      setGraphRetrieval(modelAssignments.graphRetrieval);
      setSynthesiser(modelAssignments.synthesiser);
      onClose();
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Copilot Settings</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Advanced Mode toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Advanced Mode</p>
              <p className="text-xs text-muted-foreground">
                Configure individual model assignments per pipeline stage
              </p>
            </div>
            <button
              onClick={() => setAdvancedMode(!advancedMode)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                advancedMode ? "bg-primary" : "bg-input"
              }`}
              role="switch"
              aria-checked={advancedMode}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  advancedMode ? "translate-x-4.5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {/* Model assignments — shown when advanced mode is on */}
          {advancedMode && (
            <div className="flex flex-col gap-3 border border-border rounded-md p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Model Assignments
              </p>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Router</span>
                <Input
                  value={router}
                  onChange={(e) => setRouter(e.target.value)}
                  placeholder="anthropic/claude-3-haiku-20240307"
                  className="h-7 text-xs font-mono"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Graph Retrieval</span>
                <Input
                  value={graphRetrieval}
                  onChange={(e) => setGraphRetrieval(e.target.value)}
                  placeholder="anthropic/claude-3-5-sonnet-20241022"
                  className="h-7 text-xs font-mono"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Synthesiser</span>
                <Input
                  value={synthesiser}
                  onChange={(e) => setSynthesiser(e.target.value)}
                  placeholder="anthropic/claude-sonnet-4-20250514"
                  className="h-7 text-xs font-mono"
                />
              </label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Preset manager dialog ────────────────────────────────────────────────────

const DEFAULT_PRESET_CONFIG: PresetConfig = {
  hops: 2,
  expansionLimit: 25,
  docTopK: 5,
  docRerankerK: 3,
  models: {
    router: "anthropic/claude-3-haiku-20240307",
    graphRetrieval: "anthropic/claude-3-5-sonnet-20241022",
    synthesiser: "anthropic/claude-sonnet-4-20250514",
  },
  tokenBudgets: {
    router: 500,
    graphRetrieval: 2000,
    synthesiser: 4000,
  },
  advancedMode: false,
};

interface PresetManagerDialogProps {
  open: boolean;
  onClose: () => void;
}

function PresetManagerDialog({ open, onClose }: PresetManagerDialogProps) {
  const presets = useStore((s) => s.presets);
  const upsertPreset = useStore((s) => s.upsertPreset);
  const removePreset = useStore((s) => s.removePreset);
  const addToast = useStore((s) => s.addToast);

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newHops, setNewHops] = useState("2");
  const [newLimit, setNewLimit] = useState("25");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;

    setSaving(true);
    try {
      const created = await createPreset({
        name,
        config: {
          ...DEFAULT_PRESET_CONFIG,
          hops: parseInt(newHops, 10) || 2,
          expansionLimit: parseInt(newLimit, 10) || 25,
        },
      });
      upsertPreset(created);
      setNewName("");
      setNewHops("2");
      setNewLimit("25");
      setCreating(false);
      addToast({ level: "success", title: "Preset created", duration: 3000 });
    } catch (err) {
      addToast({
        level: "error",
        title: "Failed to create preset",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(preset: PresetResponse) {
    setDeletingId(preset.id);
    try {
      await deletePreset(preset.id);
      removePreset(preset.id);
      addToast({ level: "success", title: `"${preset.name}" deleted`, duration: 3000 });
    } catch (err) {
      addToast({
        level: "error",
        title: "Failed to delete preset",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Manage Presets</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-2 max-h-72 overflow-y-auto py-1">
          {presets.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">
              No presets loaded. Copilot may be unconfigured.
            </p>
          )}
          {presets.map((preset) => (
            <div
              key={preset.id}
              className="flex items-center justify-between px-3 py-2 rounded-md border border-border"
            >
              <div className="min-w-0">
                <p className="text-xs font-medium text-foreground truncate">{preset.name}</p>
                <p className="text-[10px] text-muted-foreground">
                  {preset.is_system ? "System" : "User"} · hops:{" "}
                  {preset.config.hops} · limit: {preset.config.expansionLimit}
                </p>
              </div>
              {!preset.is_system && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-[10px] text-destructive border-destructive/30 hover:bg-destructive/10 ml-2 shrink-0"
                  onClick={() => void handleDelete(preset)}
                  disabled={deletingId === preset.id}
                >
                  {deletingId === preset.id ? "…" : "Delete"}
                </Button>
              )}
            </div>
          ))}
        </div>

        {/* New preset form */}
        {creating ? (
          <form onSubmit={(e) => void handleCreate(e)} className="flex flex-col gap-2 border-t border-border pt-3">
            <p className="text-xs font-semibold text-foreground">New Preset</p>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Preset name…"
              className="h-7 text-xs"
              required
              autoFocus
            />
            <div className="flex gap-2">
              <label className="flex-1 flex flex-col gap-1">
                <span className="text-[10px] text-muted-foreground">Hops</span>
                <Input
                  type="number"
                  min={1}
                  max={5}
                  value={newHops}
                  onChange={(e) => setNewHops(e.target.value)}
                  className="h-7 text-xs"
                />
              </label>
              <label className="flex-1 flex flex-col gap-1">
                <span className="text-[10px] text-muted-foreground">Expansion limit</span>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={newLimit}
                  onChange={(e) => setNewLimit(e.target.value)}
                  className="h-7 text-xs"
                />
              </label>
            </div>
            <div className="flex gap-2 justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setCreating(false)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={saving || !newName.trim()}>
                {saving ? "Creating…" : "Create"}
              </Button>
            </div>
          </form>
        ) : (
          <div className="border-t border-border pt-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full text-xs h-7"
              onClick={() => setCreating(true)}
            >
              + New Preset
            </Button>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Editable session name ────────────────────────────────────────────────────

function SessionName() {
  const session = useStore((s) => s.session);
  const setSession = useStore((s) => s.setSession);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  function startEdit() {
    if (!session) return;
    setDraft(session.name);
    setEditing(true);
  }

  async function commitEdit() {
    if (!session || !draft.trim()) {
      setEditing(false);
      return;
    }
    const trimmed = draft.trim();
    if (trimmed === session.name) {
      setEditing(false);
      return;
    }
    try {
      const updated = await updateSession(session.id, { name: trimmed });
      setSession(updated);
    } catch {
      // Revert silently on failure
    } finally {
      setEditing(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setEditing(false);
  }

  if (!session) return null;

  return (
    <>
      <span className="text-muted-foreground text-xs">/</span>
      {editing ? (
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          className="h-6 text-xs w-40 px-1"
          autoFocus
        />
      ) : (
        <button
          onClick={startEdit}
          title="Click to rename session"
          className="flex items-center gap-1 group max-w-48"
        >
          <span className="truncate text-xs text-muted-foreground">
            {session.name}
          </span>
          <Pencil className="h-2.5 w-2.5 text-muted-foreground opacity-0 group-hover:opacity-60 transition-opacity shrink-0" />
        </button>
      )}
    </>
  );
}

// ─── New Session dialog ───────────────────────────────────────────────────────

interface NewSessionDialogProps {
  open: boolean;
  onClose: () => void;
}

function NewSessionDialog({ open, onClose }: NewSessionDialogProps) {
  const setSession = useStore((s) => s.setSession);
  const setFindings = useStore((s) => s.setFindings);
  const clearGraph = useStore((s) => s.clearGraph);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setCreating(true);
    setError(null);
    try {
      const session = await createSession({ name: trimmed });
      clearGraph();
      setFindings([]);
      setSession(session);
      setName("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setCreating(false);
    }
  }

  function handleOpenChange(open: boolean) {
    if (!open) {
      setName("");
      setError(null);
      onClose();
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>New Session</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label
              className="text-xs font-medium text-foreground"
              htmlFor="session-name"
            >
              Session name
            </label>
            <Input
              id="session-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Investigation name…"
              className="h-8 text-xs"
              required
              autoFocus
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={creating || !name.trim()}
            >
              {creating ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Toolbar ──────────────────────────────────────────────────────────────────

export function Toolbar() {
  const session = useStore((s) => s.session);
  const setSession = useStore((s) => s.setSession);
  const setFindings = useStore((s) => s.setFindings);
  const clearGraph = useStore((s) => s.clearGraph);
  const addToast = useStore((s) => s.addToast);
  const advancedMode = useStore((s) => s.advancedMode);

  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleExport() {
    if (!session) return;
    setExporting(true);
    try {
      const blob = await exportSession(session.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${session.name.replace(/[^a-z0-9_-]/gi, "_")}.g-lab-session`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      addToast({
        level: "error",
        title: "Export failed",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setExporting(false);
    }
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset input so the same file can be re-selected
    e.target.value = "";

    setImporting(true);
    try {
      const imported = await importSession(file);
      clearGraph();
      setFindings([]);
      setSession(imported);
      addToast({
        level: "success",
        title: "Session imported",
        message: `"${imported.name}" loaded successfully.`,
        duration: 4000,
      });
    } catch (err) {
      addToast({
        level: "error",
        title: "Import failed",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setImporting(false);
    }
  }

  return (
    <>
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-card px-3 gap-3">
        {/* Left: brand + editable session name */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-foreground select-none">
            G-Lab
          </span>
          <SessionName />
        </div>

        {/* Right: preset selector + actions + status */}
        <div className="flex items-center gap-2 shrink-0">
          <PresetSelector />

          {/* Preset manager */}
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => setPresetsOpen(true)}
            title="Manage investigation presets"
          >
            Presets
          </Button>

          {/* Copilot settings */}
          <Button
            variant={advancedMode ? "default" : "outline"}
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => setSettingsOpen(true)}
            title={advancedMode ? "Copilot settings (advanced mode on)" : "Copilot settings"}
          >
            <Settings className="h-3.5 w-3.5" />
          </Button>

          {/* Export */}
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={handleExport}
            disabled={!session || exporting}
            title={session ? "Export session" : "No active session"}
          >
            <Download className="h-3.5 w-3.5" />
            {exporting ? "Exporting…" : "Export"}
          </Button>

          {/* Import (hidden file input) */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".g-lab-session"
            className="hidden"
            onChange={handleImportFile}
          />
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            title="Import session"
          >
            <Upload className="h-3.5 w-3.5" />
            {importing ? "Importing…" : "Import"}
          </Button>

          {/* New session */}
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => setNewSessionOpen(true)}
          >
            New Session
          </Button>

          <StatusDot />
          <CopilotStatusDot />
          <VectorStoreDot />
        </div>
      </header>

      <NewSessionDialog
        open={newSessionOpen}
        onClose={() => setNewSessionOpen(false)}
      />
      <CopilotSettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
      <PresetManagerDialog
        open={presetsOpen}
        onClose={() => setPresetsOpen(false)}
      />
    </>
  );
}
