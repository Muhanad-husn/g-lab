import { useRef, useState } from "react";
import { Download, Pencil, Upload } from "lucide-react";
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
import { useStore } from "@/store";
import { PRESETS, type PresetName } from "@/lib/constants";

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
  const [newSessionOpen, setNewSessionOpen] = useState(false);
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
        </div>
      </header>

      <NewSessionDialog
        open={newSessionOpen}
        onClose={() => setNewSessionOpen(false)}
      />
    </>
  );
}
