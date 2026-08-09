"""Workspace roots for Transcribe (outside any one notebook project).

``HOST_*`` vars are for Docker Compose mount sources on the host.
``TRANSCRIBE_*`` vars are what the app reads (native runs and container env).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from transcribe._bootstrap import bootstrap as _bootstrap_env

_bootstrap_env()


def _env_path(var: str) -> Path | None:
    val = os.getenv(var)
    return Path(val).expanduser() if val else None


def default_ollama_base_url() -> str:
    """Bootstrap Ollama URL via the typed env allowlist (validated when set)."""
    from transcribe.config.env_allowlist import read_env_overlays

    overlay, _ = read_env_overlays()
    ocr = overlay.get("ocr") or {}
    url = ocr.get("base_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return "http://localhost:11434"


@dataclass(frozen=True)
class RuntimePaths:
    """Canonical workspace directories. Prefer absolute paths outside the git clone."""

    repo_root: Path
    data_dir: Path
    projects_dir: Path
    inbox_dir: Path
    export_dir: Path

    def ensure_layout(self) -> None:
        for path in (
            self.data_dir,
            self.projects_dir,
            self.inbox_dir,
            self.export_dir,
            self.data_dir / "config",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def default_project_dir(self, name: str = "notebook-project") -> Path:
        return self.projects_dir / name


def _repo_root() -> Path:
    # src/transcribe/runtime_paths.py → repo root
    return Path(__file__).resolve().parent.parent.parent


def build_runtime_paths() -> RuntimePaths:
    """Resolve workspace roots from env with documented defaults."""
    repo = _repo_root()
    data_dir = _env_path("TRANSCRIBE_DATA_DIR") or (repo / "data")
    projects_dir = _env_path("TRANSCRIBE_PROJECTS_DIR") or (data_dir / "projects")
    inbox_dir = _env_path("TRANSCRIBE_INBOX_DIR") or (data_dir / "inbox")
    export_dir = _env_path("TRANSCRIBE_EXPORT_DIR") or (data_dir / "exports")
    return RuntimePaths(
        repo_root=repo,
        data_dir=data_dir,
        projects_dir=projects_dir,
        inbox_dir=inbox_dir,
        export_dir=export_dir,
    )


# Module-level snapshot (re-read via build_runtime_paths() in tests after env changes).
PATHS = build_runtime_paths()
