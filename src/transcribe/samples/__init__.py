"""Packaged sample notebook fixture (U2.2)."""

from __future__ import annotations

from pathlib import Path

DEMO_NOTEBOOK_DIR = Path(__file__).resolve().parent / "demo-notebook"


def demo_notebook_dir() -> Path:
    """Directory of placeholder page images + sidecar text."""
    return DEMO_NOTEBOOK_DIR
