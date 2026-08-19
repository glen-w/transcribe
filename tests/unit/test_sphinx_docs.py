"""Sphinx hosted docs stay a view over the in-repo Markdown corpus (I4)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

TOCTREE_RE = re.compile(r"```\{toctree\}(.*?)```", re.S)


def _toctree_entries() -> set[str]:
    text = (DOCS / "index.md").read_text(encoding="utf-8")
    found: set[str] = set()
    for block in TOCTREE_RE.findall(text):
        glob = ":glob:" in block
        entries = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not line.strip().startswith(":")
        ]
        for entry in entries:
            if glob and "*" in entry:
                for path in DOCS.glob(entry):
                    if path.suffix == ".md" and path.is_file():
                        found.add(path.relative_to(DOCS).as_posix())
            else:
                rel = entry if entry.endswith(".md") else f"{entry}.md"
                found.add(rel)
    return found


def test_sphinx_kit_files_exist():
    for rel in (
        "docs/conf.py",
        "scripts/release/build_docs.sh",
        ".readthedocs.yml",
        "docs/dev/rtd_go_live_checklist.md",
        "docs/_static/.gitkeep",
    ):
        assert (ROOT / rel).is_file(), f"missing {rel}"
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/release/build_docs.sh" in makefile
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^docs\s*=\s*\[", pyproject, re.M)
    assert "myst-parser" in pyproject
    assert "furo" in pyproject
    conf = (DOCS / "conf.py").read_text(encoding="utf-8")
    assert "myst_parser" in conf
    assert "furo" in conf
    assert "archive/**" in conf


def test_live_markdown_is_in_hosted_toctree():
    """New live docs must appear in docs/index.md (entry or glob) — no second corpus."""
    hosted = _toctree_entries()
    skip = {"index.md"}
    missing: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS).as_posix()
        if rel.startswith("archive/") or "/archive/" in rel or rel in skip:
            continue
        if rel not in hosted:
            missing.append(rel)
    assert missing == [], (
        "live docs missing from docs/index.md toctree "
        f"(add a glob or explicit entry): {missing}"
    )


def test_ci_docs_job_builds_sphinx():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip install -e \".[docs]\"" in text or "pip install -e '.[docs]'" in text
    assert "make docs" in text
    assert "docs-html" in text
    assert "needs: [compose-config, lint, tests, docs]" in text
