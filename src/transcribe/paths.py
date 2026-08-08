"""Per-project path layout and containment checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def to_posix_rel(path: Path) -> str:
    return path.as_posix()


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "project.json"

    @property
    def sources_dir(self) -> Path:
        return self.root / "sources"

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def staging_dir(self) -> Path:
        return self.root / ".staging"

    @property
    def cache_dir(self) -> Path:
        return self.root / ".cache"

    @property
    def thumbs_dir(self) -> Path:
        return self.cache_dir / "thumbs"

    @property
    def mutation_lock(self) -> Path:
        return self.root / ".transcribe.lock"

    @property
    def job_lock(self) -> Path:
        return self.root / ".transcribe.job.lock"

    def ensure_layout(self) -> None:
        for path in (
            self.sources_dir,
            self.pages_dir,
            self.results_dir,
            self.exports_dir,
            self.prompts_dir,
            self.staging_dir,
            self.thumbs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def thumb_path(self, page_id: str) -> Path:
        return self.thumbs_dir / f"{page_id}.jpg"

    def resolve_contained(self, rel: str) -> Path:
        """Resolve a stored relative path and require it stay inside the project root."""
        if not rel or rel.startswith("/") or rel.startswith("\\"):
            raise ValueError(f"absolute or empty relative path rejected: {rel!r}")
        root = self.root.resolve()
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {rel!r}") from exc
        return candidate

    def relativize(self, absolute: Path) -> str:
        root = self.root.resolve()
        resolved = absolute.resolve()
        try:
            rel = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path outside project root: {absolute}") from exc
        return to_posix_rel(rel)

    def page_render_path(self, source_id: str, page_index: int, render_id: str) -> Path:
        return (
            self.pages_dir
            / source_id
            / f"{page_index:04d}"
            / f"{render_id}.png"
        )

    def result_path(self, page_id: str) -> Path:
        return self.results_dir / f"{page_id}.json"

    def staging_attempt_dir(self, attempt_id: str) -> Path:
        return self.staging_dir / attempt_id
