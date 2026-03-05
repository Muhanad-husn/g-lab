import { useEffect, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  Link,
  Link2Off,
  Loader2,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useStore } from "@/store";
import { useDocumentActions } from "@/hooks/useDocumentActions";
import { DocumentUpload } from "./DocumentUpload";
import { PARSE_QUALITY_TIERS } from "@/lib/constants";
import type { DocumentInfo, DocumentLibrary, ParseTier } from "@/lib/types";

// ─── Parse quality badge ──────────────────────────────────────────────────────

const TIER_VARIANT: Record<ParseTier, "default" | "secondary" | "outline"> = {
  high: "default",
  standard: "secondary",
  basic: "outline",
  pending: "outline",
};

function ParseQualityBadge({ tier }: { tier: ParseTier | null }) {
  if (!tier) return null;
  const info = PARSE_QUALITY_TIERS[tier];
  return (
    <Badge variant={TIER_VARIANT[tier]} className="text-[9px] h-4 px-1">
      {info.label}
    </Badge>
  );
}

// ─── Relative time helper ─────────────────────────────────────────────────────

function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Confirm delete dialog (inline, no external dep) ─────────────────────────

interface ConfirmDeleteProps {
  name: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDelete({ name, onConfirm, onCancel }: ConfirmDeleteProps) {
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 flex flex-col gap-2">
      <p className="text-xs text-destructive">
        Delete <span className="font-semibold">"{name}"</span>? This will
        permanently remove all documents and their vectors.
      </p>
      <div className="flex gap-2 justify-end">
        <Button variant="outline" size="sm" className="h-6 text-xs" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="h-6 text-xs"
          onClick={onConfirm}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

// ─── Document row with ingest button ─────────────────────────────────────────

interface DocumentRowProps {
  doc: DocumentInfo;
  libraryId: string;
}

function DocumentRow({ doc, libraryId }: DocumentRowProps) {
  const { ingestDocument, removeDocument, fetchLibraries } =
    useDocumentActions();
  const [ingesting, setIngesting] = useState(false);
  const [tier, setTier] = useState(doc.parse_tier);
  const [chunks, setChunks] = useState(doc.chunk_count);

  const isPending = tier === "pending";

  async function handleIngest() {
    setIngesting(true);
    const result = await ingestDocument(libraryId, doc.id);
    setIngesting(false);
    if (result) {
      setTier(result.parse_tier as ParseTier);
      setChunks(result.chunk_count);
    }
  }

  async function handleRemove() {
    await removeDocument(libraryId, doc.id);
    await fetchLibraries();
  }

  return (
    <div className="flex items-center gap-1.5 px-2 py-1.5 text-xs border-b border-border/50 last:border-0">
      <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="truncate flex-1 text-foreground">{doc.filename}</span>
      {isPending ? (
        <Button
          variant="outline"
          size="sm"
          className="h-5 px-1.5 text-[10px] gap-0.5"
          onClick={handleIngest}
          disabled={ingesting}
        >
          {ingesting ? (
            <>
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              Ingesting…
            </>
          ) : (
            <>
              <Play className="h-2.5 w-2.5" />
              Ingest
            </>
          )}
        </Button>
      ) : (
        <>
          <ParseQualityBadge tier={tier as ParseTier} />
          <span className="text-[10px] text-muted-foreground shrink-0">
            {chunks} chunks
          </span>
        </>
      )}
      <button
        className="shrink-0 p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
        title="Remove document"
        onClick={handleRemove}
        aria-label="Remove document"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  );
}

// ─── Library row ──────────────────────────────────────────────────────────────

interface LibraryRowProps {
  library: DocumentLibrary;
  isAttached: boolean;
  onAttach: () => void;
  onDetach: () => void;
  onDelete: () => void;
}

function LibraryRow({
  library,
  isAttached,
  onAttach,
  onDetach,
  onDelete,
}: LibraryRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const { listDocuments: fetchDocs } = useDocumentActions();

  useEffect(() => {
    if (expanded) {
      void fetchDocs(library.id).then(setDocs);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, library.doc_count]);

  return (
    <div className="border-b border-border last:border-0">
      {/* Header row */}
      <div className="flex items-center gap-1.5 px-3 py-2">
        <button
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>

        <button
          className="flex-1 min-w-0 text-left"
          onClick={() => setExpanded((v) => !v)}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <BookOpen className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="text-xs font-medium text-foreground truncate">
              {library.name}
            </span>
            {isAttached && (
              <Badge className="text-[9px] h-4 px-1 bg-primary/20 text-primary border-primary/30">
                attached
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5 pl-4">
            <span className="text-[10px] text-muted-foreground">
              {library.doc_count} doc{library.doc_count !== 1 ? "s" : ""}
              {" · "}
              {library.chunk_count.toLocaleString()} chunks
            </span>
            <ParseQualityBadge tier={library.parse_quality} />
            <span className="text-[10px] text-muted-foreground ml-auto">
              {relativeTime(library.created_at)}
            </span>
          </div>
        </button>

        {/* Attach / detach button */}
        <button
          className={`shrink-0 p-1 rounded transition-colors ${
            isAttached
              ? "text-primary hover:text-primary/70"
              : "text-muted-foreground hover:text-foreground"
          }`}
          title={isAttached ? "Detach from session" : "Attach to session"}
          onClick={(e) => {
            e.stopPropagation();
            isAttached ? onDetach() : onAttach();
          }}
          aria-label={isAttached ? "Detach library" : "Attach library"}
        >
          {isAttached ? (
            <Link2Off className="h-3.5 w-3.5" />
          ) : (
            <Link className="h-3.5 w-3.5" />
          )}
        </button>

        {/* Delete button */}
        <button
          className="shrink-0 p-1 rounded text-muted-foreground hover:text-destructive transition-colors"
          title="Delete library"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmDelete(true);
          }}
          aria-label="Delete library"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Confirm delete */}
      {confirmDelete && (
        <div className="px-3 pb-2">
          <ConfirmDelete
            name={library.name}
            onConfirm={() => {
              setConfirmDelete(false);
              onDelete();
            }}
            onCancel={() => setConfirmDelete(false)}
          />
        </div>
      )}

      {/* Expanded: document list + upload section */}
      {expanded && !confirmDelete && (
        <div className="bg-muted/10">
          {/* Existing documents */}
          {docs.length > 0 && (
            <div className="px-3 pt-1">
              {docs.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  libraryId={library.id}
                />
              ))}
            </div>
          )}
          {/* Upload zone */}
          <div className="px-3 pb-3 pt-2">
            <DocumentUpload libraryId={library.id} />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Create library form ──────────────────────────────────────────────────────

interface CreateLibraryFormProps {
  onCreated: () => void;
  onCancel: () => void;
}

function CreateLibraryForm({ onCreated, onCancel }: CreateLibraryFormProps) {
  const { createLibrary } = useDocumentActions();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    const ok = await createLibrary(name.trim());
    setSaving(false);
    if (ok) {
      setName("");
      onCreated();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/20"
    >
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Library name…"
        className="h-7 text-xs flex-1"
        autoFocus
        disabled={saving}
      />
      <Button type="submit" size="sm" className="h-7 text-xs" disabled={saving || !name.trim()}>
        {saving ? "Creating…" : "Create"}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 text-xs"
        onClick={onCancel}
        disabled={saving}
      >
        Cancel
      </Button>
    </form>
  );
}

// ─── DocumentLibraryPanel ─────────────────────────────────────────────────────

export function DocumentLibraryPanel() {
  const libraries = useStore((s) => s.libraries);
  const attachedLibraryId = useStore((s) => s.attachedLibraryId);
  const { attachLibrary, detachLibrary, deleteLibrary } = useDocumentActions();
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {libraries.length} librar{libraries.length !== 1 ? "ies" : "y"}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs gap-1"
          onClick={() => setShowCreate((v) => !v)}
          title="New library"
        >
          <Plus className="h-3 w-3" />
          New
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateLibraryForm
          onCreated={() => setShowCreate(false)}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Library list */}
      <ScrollArea className="flex-1">
        {libraries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs gap-1">
            <BookOpen className="h-5 w-5 mb-1 opacity-40" />
            <span>No document libraries yet</span>
            <button
              className="text-primary hover:underline text-xs"
              onClick={() => setShowCreate(true)}
            >
              Create the first one
            </button>
          </div>
        ) : (
          libraries.map((lib) => (
            <LibraryRow
              key={lib.id}
              library={lib}
              isAttached={attachedLibraryId === lib.id}
              onAttach={() => void attachLibrary(lib.id)}
              onDetach={() => void detachLibrary()}
              onDelete={() => void deleteLibrary(lib.id)}
            />
          ))
        )}
      </ScrollArea>
    </div>
  );
}
