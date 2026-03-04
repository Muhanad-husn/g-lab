"""Shared fixtures for unit tests."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_data_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for test data (SQLite, logs, etc.)."""
    with tempfile.TemporaryDirectory(prefix="glab_test_") as d:
        yield Path(d)
