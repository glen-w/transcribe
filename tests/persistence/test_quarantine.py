"""Unit tests for durable journal quarantine (do not silently delete)."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.persistence.quarantine import quarantine_path


def test_quarantine_renames_beside_original(tmp_path: Path) -> None:
    path = tmp_path / ".ingest-journal.json"
    path.write_text("{not-json", encoding="utf-8")
    dest = quarantine_path(path, reason="corrupt")
    assert not path.exists()
    assert dest.exists()
    assert dest.parent == path.parent
    assert dest.name.startswith(".ingest-journal.json.corrupt.")
    assert dest.read_text(encoding="utf-8") == "{not-json"


def test_quarantine_sanitises_reason(tmp_path: Path) -> None:
    path = tmp_path / "journal.json"
    path.write_text("x", encoding="utf-8")
    dest = quarantine_path(path, reason="bad/name with spaces!")
    assert "bad_name_with_spaces_" in dest.name
    assert dest.exists()


def test_quarantine_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        quarantine_path(tmp_path / "missing.json")
