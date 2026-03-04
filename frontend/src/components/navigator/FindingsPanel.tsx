import { useState } from "react";
import { Plus, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { createFinding } from "@/api/findings";
import { useStore } from "@/store";
import type { FindingResponse } from "@/lib/types";

// ─── Finding card ─────────────────────────────────────────────────────────────

function FindingCard({ finding }: { finding: FindingResponse }) {
  const date = new Date(finding.created_at).toLocaleDateString();

  return (
    <div className="px-3 py-2 border-b border-border last:border-0">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground truncate">
            {finding.title}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground shrink-0">{date}</span>
      </div>
      {finding.body && (
        <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 pl-4">
          {finding.body}
        </p>
      )}
    </div>
  );
}

// ─── Add Finding dialog ───────────────────────────────────────────────────────

interface AddFindingDialogProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
}

function AddFindingDialog({ open, onClose, sessionId }: AddFindingDialogProps) {
  const addFinding = useStore((s) => s.addFinding);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    setSaving(true);
    setError(null);
    try {
      const finding = await createFinding(sessionId, {
        title: title.trim(),
        body: body.trim() || null,
      });
      addFinding(finding);
      setTitle("");
      setBody("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save finding");
    } finally {
      setSaving(false);
    }
  }

  function handleOpenChange(open: boolean) {
    if (!open) {
      setTitle("");
      setBody("");
      setError(null);
      onClose();
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Finding</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-foreground" htmlFor="finding-title">
              Title <span className="text-destructive">*</span>
            </label>
            <Input
              id="finding-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Finding title…"
              className="h-8 text-xs"
              required
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-foreground" htmlFor="finding-body">
              Notes{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <textarea
              id="finding-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Describe what you found…"
              rows={4}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={saving || !title.trim()}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Findings panel ───────────────────────────────────────────────────────────

export function FindingsPanel() {
  const session = useStore((s) => s.session);
  const findings = useStore((s) => s.findings);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="flex flex-col h-full">
      {/* Header row */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {findings.length} finding{findings.length !== 1 ? "s" : ""}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs gap-1"
          onClick={() => setDialogOpen(true)}
          disabled={!session}
          title={session ? "Add finding" : "No active session"}
        >
          <Plus className="h-3 w-3" />
          Add
        </Button>
      </div>

      {/* List */}
      <ScrollArea className="flex-1">
        {findings.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs gap-1">
            <span>No findings yet</span>
            {session && (
              <button
                className="text-primary hover:underline text-xs"
                onClick={() => setDialogOpen(true)}
              >
                Add the first one
              </button>
            )}
          </div>
        ) : (
          findings.map((f) => <FindingCard key={f.id} finding={f} />)
        )}
      </ScrollArea>

      {/* Dialog */}
      {session && (
        <AddFindingDialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          sessionId={session.id}
        />
      )}
    </div>
  );
}
