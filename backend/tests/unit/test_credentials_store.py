"""Tests for app.core.credentials_store."""

from pathlib import Path

from app.core.credentials_store import load_saved_credentials, save_credentials


def test_load_returns_empty_when_no_file(tmp_path: Path) -> None:
    assert load_saved_credentials(tmp_path) == {}


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    save_credentials(tmp_path, {"NEO4J_URI": "bolt://host:7687", "NEO4J_USER": "neo4j"})
    loaded = load_saved_credentials(tmp_path)
    assert loaded == {"NEO4J_URI": "bolt://host:7687", "NEO4J_USER": "neo4j"}


def test_save_merges_with_existing(tmp_path: Path) -> None:
    save_credentials(tmp_path, {"NEO4J_URI": "bolt://a:7687"})
    save_credentials(tmp_path, {"NEO4J_PASSWORD": "secret"})
    loaded = load_saved_credentials(tmp_path)
    assert loaded == {"NEO4J_URI": "bolt://a:7687", "NEO4J_PASSWORD": "secret"}


def test_empty_value_removes_key(tmp_path: Path) -> None:
    save_credentials(tmp_path, {"NEO4J_URI": "bolt://a:7687", "NEO4J_USER": "neo4j"})
    save_credentials(tmp_path, {"NEO4J_USER": ""})
    loaded = load_saved_credentials(tmp_path)
    assert loaded == {"NEO4J_URI": "bolt://a:7687"}


def test_ignores_unknown_keys(tmp_path: Path) -> None:
    save_credentials(tmp_path, {"NEO4J_URI": "bolt://a:7687", "RANDOM_KEY": "value"})
    loaded = load_saved_credentials(tmp_path)
    assert "RANDOM_KEY" not in loaded
    assert loaded == {"NEO4J_URI": "bolt://a:7687"}


def test_handles_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "credentials.json").write_text("not json!!!")
    assert load_saved_credentials(tmp_path) == {}
