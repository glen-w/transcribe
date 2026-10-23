"""U2.4 first-run path is README-linked and does not require contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
FIRST = ROOT / "docs" / "runtime" / "first_notebook.md"


def test_readme_links_first_notebook_path():
    text = README.read_text(encoding="utf-8")
    assert "docs/runtime/first_notebook.md" in text
    assert "15 minutes" in text
    assert "8510" in text


def test_first_notebook_page_is_self_contained():
    text = FIRST.read_text(encoding="utf-8")
    assert "15 minutes" in text
    assert "8510" in text
    assert "HOST_PROJECTS_DIR" in text
    assert "Open sample" in text
    assert "encrypted" in text.lower()
    assert "contracts/" not in text
    assert "docker compose up" in text
