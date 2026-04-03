"""Persist user-entered credentials to disk so they survive restarts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger: Any = get_logger(__name__)

_FILENAME = "credentials.json"

# Keys we persist (never store secrets we don't need to)
_ALLOWED_KEYS = frozenset(
    {
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "OPENROUTER_API_KEY",
    }
)


def _credentials_path(data_dir: Path) -> Path:
    return data_dir / _FILENAME


def load_saved_credentials(data_dir: Path) -> dict[str, str]:
    """Load previously saved credentials from disk.

    Returns an empty dict if the file doesn't exist or is corrupt.
    """
    path = _credentials_path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        # Only return known keys with non-empty string values
        return {
            k: v
            for k, v in raw.items()
            if k in _ALLOWED_KEYS and isinstance(v, str) and v
        }
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("credentials_load_failed", error=str(exc))
        return {}


def save_credentials(data_dir: Path, updates: dict[str, str]) -> None:
    """Merge *updates* into the saved credentials file.

    Only keys in ``_ALLOWED_KEYS`` are persisted.  Empty-string values
    remove the key (so clearing a field in the UI un-persists it).
    """
    existing = load_saved_credentials(data_dir)
    for key, value in updates.items():
        if key not in _ALLOWED_KEYS:
            continue
        if value:
            existing[key] = value
        else:
            existing.pop(key, None)

    path = _credentials_path(data_dir)
    try:
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        logger.info("credentials_saved")
    except OSError as exc:
        logger.warning("credentials_save_failed", error=str(exc))
