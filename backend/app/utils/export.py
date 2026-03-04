"""Session archive pack/unpack utilities.

Format: .g-lab-session is a ZIP archive. See ARCHITECTURE.md §6.3.
Uses only stdlib zipfile — no external dependency needed.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GLAB_VERSION = "0.1.0"
SUPPORTED_SCHEMA_VERSION = 1

# Root directory name inside the ZIP archive.
_PREFIX = "session-export"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------


def pack_session(
    session_data: dict[str, Any],
    canvas_data: dict[str, Any],
    findings_data: list[dict[str, Any]],
    action_log_ndjson: str,
    snapshots: dict[str, bytes],
) -> bytes:
    """Build a .g-lab-session ZIP archive and return raw bytes.

    Args:
        session_data:       Session metadata dict (no canvas_state key).
        canvas_data:        CanvasState dict (nodes, edges, viewport, filters).
        findings_data:      List of finding metadata dicts (no snapshot bytes).
        action_log_ndjson:  NDJSON action log content (may be empty string).
        snapshots:          Mapping of finding_id → raw PNG bytes.

    Returns:
        ZIP archive as bytes.
    """
    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "exported_at": _now_iso(),
        "glab_version": GLAB_VERSION,
        "session_id": session_data.get("id", ""),
    }

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{_PREFIX}/manifest.json", json.dumps(manifest, indent=2))
        zf.writestr(f"{_PREFIX}/session.json", json.dumps(session_data, indent=2))
        zf.writestr(f"{_PREFIX}/canvas.json", json.dumps(canvas_data, indent=2))
        zf.writestr(f"{_PREFIX}/action_log.ndjson", action_log_ndjson)
        zf.writestr(
            f"{_PREFIX}/findings/index.json",
            json.dumps(findings_data, indent=2),
        )
        for finding_id, png_bytes in snapshots.items():
            zf.writestr(
                f"{_PREFIX}/findings/snapshots/{finding_id}.png",
                png_bytes,
            )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate the archive manifest.

    Returns:
        List of warning strings (may be empty).

    Raises:
        ValueError: If schema_version is missing or incompatible.
    """
    version = manifest.get("schema_version")
    if not isinstance(version, int):
        raise ValueError("manifest.json is missing a valid integer schema_version")
    if version > SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version {version} "
            f"(this G-Lab supports up to {SUPPORTED_SCHEMA_VERSION}). "
            "Upgrade G-Lab to import this archive."
        )
    warnings: list[str] = []
    if version < SUPPORTED_SCHEMA_VERSION:
        warnings.append(
            f"Archive schema_version {version} is older than current "
            f"{SUPPORTED_SCHEMA_VERSION}; some fields may be absent."
        )
    return warnings


# ---------------------------------------------------------------------------
# Unpack
# ---------------------------------------------------------------------------


def unpack_session(zip_bytes: bytes) -> dict[str, Any]:
    """Unpack a .g-lab-session ZIP into a structured dict.

    Returns:
        {
            "manifest":          dict,
            "session":           dict,
            "canvas":            dict,
            "action_log_ndjson": str,
            "findings":          list[dict],
            "snapshots":         dict[str, bytes],  # finding_id → PNG bytes
        }

    Raises:
        ValueError: If bytes are not a valid ZIP or required entries are missing.
    """
    try:
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            names = set(zf.namelist())

            def _read_json(path: str) -> Any:
                if path not in names:
                    raise ValueError(f"Missing required archive entry: {path}")
                return json.loads(zf.read(path).decode("utf-8"))

            manifest = _read_json(f"{_PREFIX}/manifest.json")
            session = _read_json(f"{_PREFIX}/session.json")
            canvas = _read_json(f"{_PREFIX}/canvas.json")

            ndjson_entry = f"{_PREFIX}/action_log.ndjson"
            action_log_ndjson = (
                zf.read(ndjson_entry).decode("utf-8") if ndjson_entry in names else ""
            )

            findings_entry = f"{_PREFIX}/findings/index.json"
            findings: list[dict[str, Any]] = (
                _read_json(findings_entry) if findings_entry in names else []
            )

            snapshots: dict[str, bytes] = {}
            snap_prefix = f"{_PREFIX}/findings/snapshots/"
            for name in names:
                if name.startswith(snap_prefix) and name.endswith(".png"):
                    finding_id = Path(name).stem
                    snapshots[finding_id] = zf.read(name)

    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive.") from exc

    return {
        "manifest": manifest,
        "session": session,
        "canvas": canvas,
        "action_log_ndjson": action_log_ndjson,
        "findings": findings,
        "snapshots": snapshots,
    }


# ---------------------------------------------------------------------------
# Disk helpers (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def read_ndjson_if_exists(path: Path) -> str:
    """Read NDJSON file content; return empty string if file does not exist."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_ndjson(path: Path, content: str) -> None:
    """Write NDJSON content to path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
