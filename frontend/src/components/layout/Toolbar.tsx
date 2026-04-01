import { useEffect, useRef, useState } from "react";
import { ChevronDown, Clock, Download, FolderOpen, Image, Pencil, Plug, Settings, Table, Trash2, Upload } from "lucide-react";
import iconDark from "@/assets/icon-dark.svg";
import iconLight from "@/assets/icon-light.svg";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createSession, deleteSession, exportSession, importSession, listSessions, updateSession } from "@/api/sessions";
import { listFindings } from "@/api/findings";
import { getHistory } from "@/api/copilot";
import {
  createPreset,
  deletePreset,
} from "@/api/config";
import {
  getCredentials,
  updateCredentials,
  type CredentialsUpdate,
} from "@/api/credentials";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useStore } from "@/store";
import { PRESETS, type PresetName } from "@/lib/constants";
import type { GraphEdge, GraphNode, PresetConfig, PresetResponse } from "@/lib/types";
import { captureCanvasSnapshot } from "@/lib/cytoscapeRef";

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

// ─── Credentials dialog ───────────────────────────────────────────────────────

interface CredentialsDialogProps {
  open: boolean;
  onClose: () => void;
}

function CredentialsDialog({ open, onClose }: CredentialsDialogProps) {
  const addToast = useStore((s) => s.addToast);

  const [neo4jUri, setNeo4jUri] = useState("");
  const [neo4jUser, setNeo4jUser] = useState("");
  const [neo4jPassword, setNeo4jPassword] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [origUri, setOrigUri] = useState("");
  const [origUser, setOrigUser] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleOpen() {
    setLoading(true);
    try {
      const status = await getCredentials();
      setNeo4jUri(status.neo4j_uri);
      setNeo4jUser(status.neo4j_user);
      setOrigUri(status.neo4j_uri);
      setOrigUser(status.neo4j_user);
      setNeo4jPassword("");
      setOpenrouterKey("");
    } catch {
      // Start with empty fields if fetch fails
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const update: CredentialsUpdate = {};
      if (neo4jUri.trim() && neo4jUri !== origUri) update.neo4j_uri = neo4jUri.trim();
      if (neo4jUser.trim() && neo4jUser !== origUser) update.neo4j_user = neo4jUser.trim();
      if (neo4jPassword) update.neo4j_password = neo4jPassword;
      if (openrouterKey.trim()) update.openrouter_api_key = openrouterKey.trim();

      if (Object.keys(update).length === 0) {
        onClose();
        return;
      }

      const status = await updateCredentials(update);
      const neo4jOk = status.neo4j_connected;
      const orOk = status.openrouter_configured;

      addToast({
        level: neo4jOk || orOk ? "success" : "error",
        title: "Credentials updated",
        message: [
          neo4jOk ? "Neo4j connected" : "Neo4j not connected",
          orOk ? "Copilot ready" : "Copilot not configured",
        ].join(" · "),
        duration: 5000,
      });
      onClose();
    } catch (err) {
      addToast({
        level: "error",
        title: "Failed to update credentials",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  }

  function handleOpenChange(isOpen: boolean) {
    if (isOpen) {
      void handleOpen();
    } else {
      onClose();
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connection Settings</DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="py-6 text-center text-xs text-muted-foreground">
            Loading…
          </div>
        ) : (
          <div className="flex flex-col gap-4 py-2">
            {/* Neo4j */}
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Neo4j
              </p>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">URI</span>
                <Input
                  value={neo4jUri}
                  onChange={(e) => setNeo4jUri(e.target.value)}
                  placeholder="bolt://localhost:7687"
                  className="h-7 text-xs font-mono"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Username</span>
                <Input
                  value={neo4jUser}
                  onChange={(e) => setNeo4jUser(e.target.value)}
                  placeholder="neo4j"
                  className="h-7 text-xs"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">
                  Password{" "}
                  <span className="text-muted-foreground font-normal">
                    (leave blank to keep current)
                  </span>
                </span>
                <Input
                  type="password"
                  value={neo4jPassword}
                  onChange={(e) => setNeo4jPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-7 text-xs"
                />
              </label>
            </div>

            {/* OpenRouter */}
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                OpenRouter
              </p>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">
                  API Key{" "}
                  <span className="text-muted-foreground font-normal">
                    (leave blank to keep current)
                  </span>
                </span>
                <Input
                  type="password"
                  value={openrouterKey}
                  onChange={(e) => setOpenrouterKey(e.target.value)}
                  placeholder="sk-or-…"
                  className="h-7 text-xs font-mono"
                />
              </label>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void handleSave()} disabled={saving || loading}>
            {saving ? "Connecting…" : "Save & Connect"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Preset selector ──────────────────────────────────────────────────────────

function PresetSelector() {
  const activePreset = useStore((s) => s.activePreset);
  const setPreset = useStore((s) => s.setPreset);

  return (
    <Select value={activePreset} onValueChange={(v) => setPreset(v as PresetName)}>
      <SelectTrigger className="h-8 w-[140px] text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.values(PRESETS).map((p) => (
          <SelectItem key={p.name} value={p.name} className="text-xs">
            {p.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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
                  placeholder="anthropic/claude-haiku-4-5"
                  className="h-7 text-xs font-mono"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Graph Retrieval</span>
                <Input
                  value={graphRetrieval}
                  onChange={(e) => setGraphRetrieval(e.target.value)}
                  placeholder="anthropic/claude-sonnet-4"
                  className="h-7 text-xs font-mono"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-foreground">Synthesiser</span>
                <Input
                  value={synthesiser}
                  onChange={(e) => setSynthesiser(e.target.value)}
                  placeholder="anthropic/claude-sonnet-4"
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
    router: "anthropic/claude-haiku-4-5",
    graphRetrieval: "anthropic/claude-sonnet-4",
    synthesiser: "anthropic/claude-sonnet-4",
  },
  tokenBudgets: {
    router: 500,
    graphRetrieval: 2000,
    synthesiser: 4000,
    contextWindow: 128000,
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

// ─── Session Picker dialog ───────────────────────────────────────────────────

interface SessionPickerDialogProps {
  open: boolean;
  onClose: () => void;
}

function SessionPickerDialog({ open, onClose }: SessionPickerDialogProps) {
  const currentSession = useStore((s) => s.session);
  const setSession = useStore((s) => s.setSession);
  const setFindings = useStore((s) => s.setFindings);
  const clearGraph = useStore((s) => s.clearGraph);
  const loadHistory = useStore((s) => s.loadHistory);
  const addToast = useStore((s) => s.addToast);

  const [sessions, setSessions] = useState<
    Array<{ id: string; name: string; updated_at: string; status: string }>
  >([]);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Fetch session list when dialog opens
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    listSessions()
      .then((list) => {
        if (!cancelled) setSessions(list);
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function handleSwitch(sessionId: string) {
    if (sessionId === currentSession?.id) return;
    setSwitching(sessionId);
    try {
      const picked = sessions.find((s) => s.id === sessionId);
      if (!picked) return;

      // Clear current state
      clearGraph();
      setFindings([]);
      loadHistory([]);

      // Set the new session (we already have the data from list)
      setSession(picked as import("@/lib/types").SessionResponse);

      // Fetch findings + history for the new session (non-critical)
      try {
        const findings = await listFindings(sessionId);
        setFindings(findings);
      } catch {
        // non-critical
      }
      try {
        const messages = await getHistory(sessionId);
        loadHistory(messages);
      } catch {
        // non-critical
      }

      addToast({
        level: "success",
        title: "Session switched",
        message: `Now working on "${picked.name}".`,
        duration: 3000,
      });
      onClose();
    } catch (err) {
      addToast({
        level: "error",
        title: "Switch failed",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setSwitching(null);
    }
  }

  async function handleDelete(sessionId: string) {
    if (sessionId === currentSession?.id) return;
    setDeleting(sessionId);
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      addToast({
        level: "success",
        title: "Session deleted",
        duration: 3000,
      });
    } catch (err) {
      addToast({
        level: "error",
        title: "Delete failed",
        message: err instanceof Error ? err.message : "Unknown error",
        duration: 5000,
      });
    } finally {
      setDeleting(null);
    }
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Switch Session</DialogTitle>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Loading sessions…
          </p>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No sessions found.
          </p>
        ) : (
          <ScrollArea className="max-h-80">
            <div className="flex flex-col gap-1 pr-3">
              {sessions.map((s) => {
                const isCurrent = s.id === currentSession?.id;
                return (
                  <div
                    key={s.id}
                    className={`flex items-center justify-between rounded-md px-3 py-2 text-sm ${
                      isCurrent
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-muted/50 cursor-pointer"
                    }`}
                    onClick={() => !isCurrent && handleSwitch(s.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !isCurrent) handleSwitch(s.id);
                    }}
                  >
                    <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                      <span className="font-medium truncate">
                        {s.name}
                        {isCurrent && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            (current)
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDate(s.updated_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 ml-2 shrink-0">
                      {switching === s.id && (
                        <span className="text-xs text-muted-foreground">
                          Loading…
                        </span>
                      )}
                      {!isCurrent && !switching && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(s.id);
                          }}
                          disabled={deleting === s.id}
                          title="Delete session"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Canvas export helpers ────────────────────────────────────────────────────

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportCanvasPng(sessionName: string): boolean {
  const dataUrl = captureCanvasSnapshot();
  if (!dataUrl) return false;
  const byteString = atob(dataUrl.split(",")[1]);
  const mimeString = dataUrl.split(",")[0].split(":")[1].split(";")[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  const blob = new Blob([ab], { type: mimeString });
  const safeName = sessionName.replace(/[^a-z0-9_-]/gi, "_");
  downloadBlob(blob, `${safeName}_canvas.png`);
  return true;
}

function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function exportCanvasCsv(
  nodes: GraphNode[],
  edges: GraphEdge[],
  sessionName: string,
): boolean {
  if (nodes.length === 0) return false;

  const lines: string[] = [];

  // Nodes sheet
  lines.push("# Nodes");
  lines.push("id,labels,properties");
  for (const node of nodes) {
    lines.push(
      [
        escapeCsvField(node.id),
        escapeCsvField(node.labels.join(";")),
        escapeCsvField(JSON.stringify(node.properties)),
      ].join(","),
    );
  }

  lines.push("");

  // Edges sheet
  lines.push("# Edges");
  lines.push("id,type,source,target,properties");
  for (const edge of edges) {
    lines.push(
      [
        escapeCsvField(edge.id),
        escapeCsvField(edge.type),
        escapeCsvField(edge.source),
        escapeCsvField(edge.target),
        escapeCsvField(JSON.stringify(edge.properties)),
      ].join(","),
    );
  }

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const safeName = sessionName.replace(/[^a-z0-9_-]/gi, "_");
  downloadBlob(blob, `${safeName}_canvas.csv`);
  return true;
}

// ─── Toolbar ──────────────────────────────────────────────────────────────────

export function Toolbar() {
  const session = useStore((s) => s.session);
  const setSession = useStore((s) => s.setSession);
  const setFindings = useStore((s) => s.setFindings);
  const clearGraph = useStore((s) => s.clearGraph);
  const addToast = useStore((s) => s.addToast);
  const advancedMode = useStore((s) => s.advancedMode);
  const nodeCount = useStore((s) => s.nodes.length);

  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [sessionPickerOpen, setSessionPickerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [credentialsOpen, setCredentialsOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
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
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-card px-3 gap-3 shadow-[0_1px_3px_0_rgba(0,0,0,0.3)]">
        {/* Left: brand + editable session name */}
        <div className="flex items-center gap-2 min-w-0">
          <img src={iconLight} alt="G-Lab" className="h-6 w-6 dark:hidden" />
          <img src={iconDark} alt="G-Lab" className="h-6 w-6 hidden dark:block" />
          <span className="text-sm font-semibold text-foreground select-none">
            G-Lab
          </span>
          <SessionName />
        </div>

        {/* Right: grouped actions + status */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Group 1: Preset selector + manager */}
          <div className="flex items-center gap-2">
            <PresetSelector />
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setPresetsOpen(true)}
              title="Manage investigation presets"
            >
              Presets
            </Button>
          </div>

          <Separator orientation="vertical" className="h-5" />

          {/* Group 2: Connect + Copilot settings */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setCredentialsOpen(true)}
              title="Connection settings (Neo4j + OpenRouter)"
            >
              <Plug className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={advancedMode ? "default" : "outline"}
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setSettingsOpen(true)}
              title={advancedMode ? "Copilot settings (advanced mode on)" : "Copilot settings"}
            >
              <Settings className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Separator orientation="vertical" className="h-5" />

          {/* Group 3: Export / Import / Clear / New Session */}
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 text-xs"
                  disabled={!session || exporting}
                  title={session ? "Export options" : "No active session"}
                >
                  <Download className="h-3.5 w-3.5" />
                  {exporting ? "Exporting…" : "Export"}
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() => void handleExport()}
                  disabled={exporting}
                >
                  <Download className="h-3.5 w-3.5 mr-2" />
                  Session (.g-lab-session)
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    if (!session) return;
                    const ok = exportCanvasPng(session.name);
                    if (!ok)
                      addToast({
                        level: "error",
                        title: "PNG export failed",
                        message: "Canvas is empty or not mounted.",
                        duration: 4000,
                      });
                  }}
                  disabled={nodeCount === 0}
                >
                  <Image className="h-3.5 w-3.5 mr-2" />
                  Canvas as PNG
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    if (!session) return;
                    const ok = exportCanvasCsv(
                      useStore.getState().nodes,
                      useStore.getState().edges,
                      session.name,
                    );
                    if (!ok)
                      addToast({
                        level: "error",
                        title: "CSV export failed",
                        message: "Canvas is empty.",
                        duration: 4000,
                      });
                  }}
                  disabled={nodeCount === 0}
                >
                  <Table className="h-3.5 w-3.5 mr-2" />
                  Canvas as CSV
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setClearOpen(true)}
              disabled={nodeCount === 0}
              title="Clear canvas"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setSessionPickerOpen(true)}
              title="Switch session"
            >
              <FolderOpen className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setNewSessionOpen(true)}
            >
              New Session
            </Button>
          </div>

          <Separator orientation="vertical" className="h-5" />

          {/* Group 4: Status dots */}
          <div className="flex items-center gap-3 rounded-md bg-muted/30 px-2.5 py-1">
            <StatusDot />
            <CopilotStatusDot />
            <VectorStoreDot />
          </div>
        </div>
      </header>

      {/* Clear canvas confirmation */}
      <Dialog open={clearOpen} onOpenChange={setClearOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear Canvas</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will remove all {nodeCount} node{nodeCount !== 1 ? "s" : ""} and
            their edges from the canvas. This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setClearOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                clearGraph();
                setClearOpen(false);
              }}
            >
              Clear All
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SessionPickerDialog
        open={sessionPickerOpen}
        onClose={() => setSessionPickerOpen(false)}
      />
      <NewSessionDialog
        open={newSessionOpen}
        onClose={() => setNewSessionOpen(false)}
      />
      <CredentialsDialog
        open={credentialsOpen}
        onClose={() => setCredentialsOpen(false)}
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
