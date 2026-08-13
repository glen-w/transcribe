"""Core packages must not import Streamlit (UI stays at the boundary)."""

from __future__ import annotations

import ast
from pathlib import Path

_CORE_ROOT = Path(__file__).resolve().parents[2] / "src" / "transcribe"
_SKIP_PARTS = {"ui"}


def _python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def test_core_packages_do_not_import_streamlit() -> None:
    offenders: list[str] = []
    for path in _python_files(_CORE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "streamlit" or alias.name.startswith("streamlit."):
                        offenders.append(str(path.relative_to(_CORE_ROOT.parent)))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "streamlit" or mod.startswith("streamlit."):
                    offenders.append(str(path.relative_to(_CORE_ROOT.parent)))
    assert offenders == []
