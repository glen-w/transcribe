"""Corpus registration and corpus-aware notebook discovery helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from transcribe.corpus.index import CorpusIndex, CorpusIndexStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.schema import require_format
from transcribe.ports import Clock, SystemClock, to_iso


def ensure_registered(
    corpus_paths: CorpusPaths,
    project_root: Path,
    project_id: str,
    *,
    clock: Clock | None = None,
) -> None:
    """Register an existing project root in the corpus index."""
    root = Path(project_root).expanduser().resolve()
    projects = corpus_paths.projects_dir.expanduser().resolve()
    rel = root.relative_to(projects).as_posix()
    payload = require_format(read_json(root / "project.json"), "transcribe.project")
    actual_id = str(payload["id"])
    if actual_id != project_id:
        raise CorpusError(f"project id {actual_id!r} != expected {project_id!r}")
    CorpusIndexStore(corpus_paths, clock=clock or SystemClock()).register_notebook(
        notebook_id=project_id,
        managed_relpath=rel,
        project_id=actual_id,
    )


def register_project_in_corpus(
    corpus_paths: CorpusPaths,
    project_root: Path,
    project_id: str,
    *,
    clock: Clock | None = None,
) -> None:
    ensure_registered(
        corpus_paths, project_root=project_root, project_id=project_id, clock=clock
    )


def unregister_notebook(
    corpus_paths: CorpusPaths,
    notebook_id: str,
    *,
    clock: Clock | None = None,
) -> None:
    """Remove a notebook from the corpus index (does not delete on-disk files)."""
    CorpusIndexStore(corpus_paths, clock=clock or SystemClock()).unregister_notebook(
        notebook_id
    )


def discover_roots(
    corpus_paths: CorpusPaths,
    *,
    register_on_discover: bool = False,
    clock: Clock | None = None,
) -> list[Path]:
    """Prefer the corpus index; fall back to project folder scan when absent."""
    store = CorpusIndexStore(corpus_paths, clock=clock or SystemClock())
    try:
        index = store.load()
    except CorpusError:
        _quarantine_index(corpus_paths)
        return rebuild_index_from_projects(corpus_paths, clock=clock)
    if index is not None:
        return [corpus_paths.resolve_managed(e.managed_relpath) for e in index.entries]
    roots = _scan_project_roots(corpus_paths.projects_dir)
    if register_on_discover:
        for root in roots:
            project_id = _project_id(root)
            ensure_registered(corpus_paths, root, project_id, clock=clock)
    return roots


def discover_corpus_project_roots(corpus_paths: CorpusPaths) -> list[Path]:
    return discover_roots(corpus_paths)


def rebuild_index_from_projects(
    corpus_paths: CorpusPaths,
    *,
    clock: Clock | None = None,
) -> list[Path]:
    """Rebuild index entries from authoritative project.json IDs."""
    if corpus_paths.index_path.exists():
        try:
            CorpusIndex.from_dict(read_json(corpus_paths.index_path))
        except Exception:
            _quarantine_index(corpus_paths)
    now = to_iso((clock or SystemClock()).now())
    entries = []
    roots = _scan_project_roots(corpus_paths.projects_dir)
    for root in roots:
        rel = root.resolve().relative_to(corpus_paths.projects_dir.resolve()).as_posix()
        entries.append(
            {
                "notebook_id": _project_id(root),
                "managed_relpath": rel,
                "registered_at": now,
                "updated_at": now,
            }
        )
    index = CorpusIndex.from_dict(
        {
            "format": "transcribe.corpus-index",
            "schema_version": 1,
            "updated_at": now,
            "entries": entries,
        }
    )
    corpus_paths.ensure_layout()
    write_json_atomic(corpus_paths.index_path, index.as_dict())
    return roots


def _scan_project_roots(projects_dir: Path) -> list[Path]:
    if not projects_dir.exists():
        return []
    return [
        child.resolve()
        for child in sorted(projects_dir.iterdir())
        if child.is_dir() and (child / "project.json").exists()
    ]


def _project_id(root: Path) -> str:
    payload = require_format(read_json(root / "project.json"), "transcribe.project")
    return str(payload["id"])


def _quarantine_index(corpus_paths: CorpusPaths) -> None:
    if not corpus_paths.index_path.exists():
        return
    corpus_paths.quarantine_dir.mkdir(parents=True, exist_ok=True)
    dest = corpus_paths.quarantine_dir / f"{corpus_paths.index_path.name}.corrupt"
    n = 1
    while dest.exists():
        n += 1
        dest = corpus_paths.quarantine_dir / f"{corpus_paths.index_path.name}.corrupt-{n}"
    shutil.move(str(corpus_paths.index_path), str(dest))
