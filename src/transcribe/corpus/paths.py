"""Workspace corpus paths (bulk-import generation)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcribe.runtime_paths import RuntimePaths


@dataclass(frozen=True)
class CorpusPaths:
    """Durable corpus authority under ``{data_dir}/corpus/``."""

    data_dir: Path
    projects_dir: Path

    @classmethod
    def from_runtime(cls, runtime: RuntimePaths) -> CorpusPaths:
        return cls(data_dir=runtime.data_dir, projects_dir=runtime.projects_dir)

    @property
    def root(self) -> Path:
        return self.data_dir / "corpus"

    @property
    def index_path(self) -> Path:
        return self.root / "corpus-index.json"

    @property
    def lock_path(self) -> Path:
        return self.root / ".corpus.lock"

    @property
    def import_runs_dir(self) -> Path:
        return self.root / "import-runs"

    @property
    def ocr_runs_dir(self) -> Path:
        return self.root / "ocr-runs"

    @property
    def analysis_batch_runs_dir(self) -> Path:
        """Workspace multi-notebook Analyse batch runs (not per-project analysis/runs)."""
        return self.root / "analysis-runs"

    @property
    def quarantine_dir(self) -> Path:
        return self.root / "quarantine"

    def import_run_path(self, import_run_id: str) -> Path:
        return self.import_runs_dir / f"{import_run_id}.json"

    def ocr_run_path(self, ocr_run_id: str) -> Path:
        return self.ocr_runs_dir / f"{ocr_run_id}.json"

    def analysis_batch_run_path(self, analysis_batch_id: str) -> Path:
        return self.analysis_batch_runs_dir / f"{analysis_batch_id}.json"

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.import_runs_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_runs_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_batch_runs_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def resolve_managed(self, managed_relpath: str) -> Path:
        """Resolve a corpus entry locator under projects_dir with containment."""
        if (
            not managed_relpath
            or managed_relpath.startswith("/")
            or managed_relpath.startswith("\\")
        ):
            raise ValueError(f"absolute or empty managed_relpath rejected: {managed_relpath!r}")
        root = self.projects_dir.resolve()
        candidate = (self.projects_dir / managed_relpath).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"managed_relpath escapes projects_dir: {managed_relpath!r}") from exc
        return candidate
