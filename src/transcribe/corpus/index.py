"""Durable workspace corpus index (``transcribe.corpus-index``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, ValidationError
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, SystemClock, to_iso


@dataclass
class CorpusEntry:
    notebook_id: str
    managed_relpath: str
    registered_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "notebook_id": self.notebook_id,
            "managed_relpath": self.managed_relpath,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusEntry:
        return cls(
            notebook_id=str(data["notebook_id"]),
            managed_relpath=str(data["managed_relpath"]),
            registered_at=str(data["registered_at"]),
            updated_at=str(data["updated_at"]),
        )


@dataclass
class CorpusIndex:
    updated_at: str
    entries: list[CorpusEntry] = field(default_factory=list)
    format: str = "transcribe.corpus-index"
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "entries": [e.as_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusIndex:
        require_format(data, "transcribe.corpus-index")
        return cls(
            updated_at=str(data.get("updated_at") or ""),
            entries=[CorpusEntry.from_dict(e) for e in data.get("entries") or []],
            format=str(data.get("format", "transcribe.corpus-index")),
            schema_version=int(data.get("schema_version", 1)),
        )

    def notebook_ids(self) -> list[str]:
        return [e.notebook_id for e in self.entries]


def validate_corpus_index(index: CorpusIndex, *, paths: CorpusPaths) -> None:
    """Structural + locator uniqueness/containment (does not open every project.json)."""
    if index.format != "transcribe.corpus-index":
        raise ValidationError(f"unexpected corpus-index format: {index.format!r}")
    if index.schema_version != 1:
        raise ValidationError(
            f"unsupported corpus-index schema_version {index.schema_version}"
        )
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in index.entries:
        nid = entry.notebook_id.strip()
        if not nid:
            raise ValidationError("corpus entry notebook_id must be non-empty")
        if nid in seen_ids:
            raise ValidationError(f"duplicate notebook_id in corpus index: {nid}")
        seen_ids.add(nid)
        rel = entry.managed_relpath.strip()
        if not rel:
            raise ValidationError(f"corpus entry {nid} managed_relpath must be non-empty")
        if rel in seen_paths:
            raise ValidationError(f"duplicate managed_relpath in corpus index: {rel}")
        seen_paths.add(rel)
        try:
            paths.resolve_managed(rel)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


def validate_entry_matches_project(
    *,
    notebook_id: str,
    project_id: str,
) -> None:
    if notebook_id != project_id:
        raise ValidationError(
            f"notebook_id {notebook_id!r} != project.id {project_id!r}"
        )


class CorpusIndexStore:
    """Load/save corpus index under the corpus lock."""

    def __init__(
        self,
        paths: CorpusPaths,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.paths = paths
        self.clock = clock or SystemClock()

    def load(self) -> CorpusIndex | None:
        """Return index or None if absent (bulk import not used in this workspace yet)."""
        if not self.paths.index_path.exists():
            return None
        try:
            payload = read_json(self.paths.index_path)
            index = CorpusIndex.from_dict(payload)
            validate_corpus_index(index, paths=self.paths)
            return index
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            raise CorpusError(f"failed to load corpus index: {exc}") from exc

    def save(self, index: CorpusIndex) -> None:
        validate_corpus_index(index, paths=self.paths)
        self.paths.ensure_layout()
        with mutation_lock(self.paths.lock_path):
            write_json_atomic(self.paths.index_path, index.as_dict())

    def register_notebook(
        self,
        *,
        notebook_id: str,
        managed_relpath: str,
        project_id: str | None = None,
    ) -> CorpusIndex:
        """Append or refresh a notebook entry. Holds corpus lock only."""
        if project_id is not None:
            validate_entry_matches_project(
                notebook_id=notebook_id, project_id=project_id
            )
        # Containment check before lock
        self.paths.resolve_managed(managed_relpath)
        self.paths.ensure_layout()
        now = to_iso(self.clock.now())
        with mutation_lock(self.paths.lock_path):
            if self.paths.index_path.exists():
                index = CorpusIndex.from_dict(read_json(self.paths.index_path))
            else:
                index = CorpusIndex(updated_at=now, entries=[])
            for entry in index.entries:
                if entry.notebook_id == notebook_id:
                    entry.managed_relpath = managed_relpath
                    entry.updated_at = now
                    index.updated_at = now
                    validate_corpus_index(index, paths=self.paths)
                    write_json_atomic(self.paths.index_path, index.as_dict())
                    return index
                if entry.managed_relpath == managed_relpath:
                    raise CorpusError(
                        f"managed_relpath already registered to {entry.notebook_id}: "
                        f"{managed_relpath}"
                    )
            index.entries.append(
                CorpusEntry(
                    notebook_id=notebook_id,
                    managed_relpath=managed_relpath,
                    registered_at=now,
                    updated_at=now,
                )
            )
            index.updated_at = now
            validate_corpus_index(index, paths=self.paths)
            write_json_atomic(self.paths.index_path, index.as_dict())
            return index

    def unregister_notebook(self, notebook_id: str) -> CorpusIndex | None:
        """Remove a notebook entry from the corpus index. No-op if absent/missing index."""
        nid = notebook_id.strip()
        if not nid:
            raise ValidationError("notebook_id must be non-empty")
        self.paths.ensure_layout()
        now = to_iso(self.clock.now())
        with mutation_lock(self.paths.lock_path):
            if not self.paths.index_path.exists():
                return None
            index = CorpusIndex.from_dict(read_json(self.paths.index_path))
            before = len(index.entries)
            index.entries = [e for e in index.entries if e.notebook_id != nid]
            if len(index.entries) == before:
                return index
            index.updated_at = now
            validate_corpus_index(index, paths=self.paths)
            write_json_atomic(self.paths.index_path, index.as_dict())
            return index


def ordered_corpus_then_notebook_lock(
    corpus_lock: Path,
    notebook_lock: Path,
    *,
    timeout: float = 30.0,
):
    """Acquire corpus lock then notebook mutation lock (never reverse)."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        with mutation_lock(corpus_lock, timeout=timeout):
            with mutation_lock(notebook_lock, timeout=timeout):
                yield

    return _cm()
