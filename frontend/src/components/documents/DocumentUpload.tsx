import { useRef, useState } from "react";
import { Upload, X, FileText, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";
import { useDocumentActions } from "@/hooks/useDocumentActions";
import { MAX_DOC_UPLOAD_SIZE_MB } from "@/lib/constants";
import type { DocumentUploadResponse } from "@/lib/types";

// ─── Accepted MIME types ───────────────────────────────────────────────────────

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
} as const;

const ACCEPTED_MIME = Object.keys(ACCEPTED).join(",");

// ─── ParseTier badge ──────────────────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  high: "bg-green-500/20 text-green-400 border-green-500/30",
  standard: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  basic: "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

function TierBadge({ tier }: { tier: string }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${(TIER_COLORS[tier] ?? TIER_COLORS.basic)}`}
    >
      {tier}
    </span>
  );
}

// ─── UploadResult row ─────────────────────────────────────────────────────────

interface UploadResultRowProps {
  result: DocumentUploadResponse;
}

function UploadResultRow({ result }: UploadResultRowProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-border last:border-0">
      <CheckCircle className="h-3 w-3 shrink-0 text-green-400" />
      <span className="truncate flex-1 text-foreground">{result.filename}</span>
      <TierBadge tier={result.parse_tier} />
      <span className="text-muted-foreground shrink-0 text-[10px]">
        {result.chunk_count} chunks
      </span>
    </div>
  );
}

// ─── DocumentUpload ───────────────────────────────────────────────────────────

interface DocumentUploadProps {
  libraryId: string;
}

export function DocumentUpload({ libraryId }: DocumentUploadProps) {
  const isUploading = useStore((s) => s.isUploading);
  const { uploadFiles } = useDocumentActions();

  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [results, setResults] = useState<DocumentUploadResponse[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  function validateFiles(files: File[]): string | null {
    for (const f of files) {
      if (f.size > MAX_DOC_UPLOAD_SIZE_MB * 1024 * 1024) {
        return `${f.name} exceeds the ${MAX_DOC_UPLOAD_SIZE_MB} MB limit.`;
      }
      const allowed = ["application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
      if (!allowed.includes(f.type)) {
        return `${f.name} is not a supported type. Only PDF and DOCX are accepted.`;
      }
    }
    return null;
  }

  async function handleFiles(files: File[]) {
    setUploadError(null);
    setResults([]);

    const validationError = validateFiles(files);
    if (validationError) {
      setUploadError(validationError);
      return;
    }

    const uploaded = await uploadFiles(libraryId, files);
    if (uploaded === null) {
      setUploadError("Upload failed. Check the banner for details.");
    } else {
      setResults(uploaded);
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      void handleFiles(Array.from(e.target.files));
      // Reset so the same file can be re-uploaded
      e.target.value = "";
    }
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) void handleFiles(files);
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(true);
  }

  function onDragLeave() {
    setDragging(false);
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload files — click or drag and drop"
        className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-6 cursor-pointer transition-colors ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/30"
        } ${isUploading ? "pointer-events-none opacity-60" : ""}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        <Upload className="h-5 w-5 text-muted-foreground" />
        <p className="text-xs text-muted-foreground text-center">
          {isUploading
            ? "Uploading…"
            : "Drop PDF or DOCX files here, or click to browse"}
        </p>
        <p className="text-[10px] text-muted-foreground/60">
          Max {MAX_DOC_UPLOAD_SIZE_MB} MB per file
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_MIME}
        multiple
        className="hidden"
        onChange={onInputChange}
      />

      {/* Upload error */}
      {uploadError && (
        <div className="flex items-start gap-1.5 rounded-md bg-destructive/10 border border-destructive/30 px-2.5 py-1.5">
          <AlertCircle className="h-3 w-3 shrink-0 text-destructive mt-0.5" />
          <p className="text-xs text-destructive">{uploadError}</p>
          <button
            className="ml-auto shrink-0"
            onClick={() => setUploadError(null)}
            aria-label="Dismiss error"
          >
            <X className="h-3 w-3 text-destructive/60 hover:text-destructive" />
          </button>
        </div>
      )}

      {/* Upload results */}
      {results.length > 0 && (
        <div className="rounded-md border border-border overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1 bg-muted/30 border-b border-border">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <FileText className="h-3 w-3" />
              Uploaded
            </span>
            <button onClick={() => setResults([])} aria-label="Clear results">
              <X className="h-3 w-3 text-muted-foreground hover:text-foreground" />
            </button>
          </div>
          {results.map((r) => (
            <UploadResultRow key={r.document_id} result={r} />
          ))}
        </div>
      )}

      {/* Hidden upload button for accessibility */}
      <Button
        variant="outline"
        size="sm"
        className="text-xs h-7"
        disabled={isUploading}
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="h-3 w-3 mr-1.5" />
        {isUploading ? "Uploading…" : "Browse files"}
      </Button>
    </div>
  );
}
