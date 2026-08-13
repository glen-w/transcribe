"""Shared multi-notebook candidate discovery for bulk OCR / Analyse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcribe.corpus.import_run import ImportRunStore, committed_notebook_ids
from transcribe.corpus.index import CorpusIndexStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, TranscribeError, ValidationError
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator
from transcribe.services.archive import discover_project_roots
from transcribe.services.project import ProjectService, open_project_paths


@dataclass
class NotebookCandidate:
    notebook_id: str
    title: str
    root: Path
    managed_relpath: str
    pages_total: int = 0
    pages_pending: int = 0
    pages_failed: int = 0
    pages_with_text: int = 0
    analysis_aggregate: str = "missing"


# Backward-compatible alias used by batch OCR.
BatchCandidate = NotebookCandidate


def _managed_relpath(corpus: CorpusPaths, root: Path) -> str:
    try:
        return root.resolve().relative_to(corpus.projects_dir.resolve()).as_posix()
    except ValueError:
        return root.name


def page_counts(projects: ProjectService, project) -> tuple[int, int, int]:
    """Return (total, pending_or_failed, failed) page counts."""
    total = len(project.pages)
    pending = 0
    failed = 0
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        if result is None or result.status != "succeeded":
            pending += 1
        if result is not None and result.status == "failed":
            failed += 1
    return total, pending, failed


def pages_with_text_count(projects: ProjectService, project) -> int:
    count = 0
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        text = result.effective_text() if result else None
        if text and str(text).strip():
            count += 1
    return count


def analysis_aggregate_for_project(
    projects: ProjectService,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> str:
    """Lightweight aggregate health for candidate captions / pending filter."""
    from transcribe.analysis.health import derive_analysis_health
    from transcribe.analysis.runner import AnalysisRunner
    from transcribe.analysis.storage import AnalysisStorage

    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    analysis_dir = projects.paths.analysis_dir
    if not analysis_dir.is_dir():
        return "missing"
    module_ids = sorted(
        p.name
        for p in analysis_dir.iterdir()
        if p.is_dir()
        and p.name != "runs"
        and (p / "published.json").is_file()
    )
    if not module_ids:
        return "missing"
    storage = AnalysisStorage(projects.paths)
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    try:
        health = derive_analysis_health(
            storage=storage,
            runner=runner,
            module_ids=module_ids,
            content_revision=projects.content_revision(),
        )
    except (OSError, ValueError, KeyError, TypeError, TranscribeError):
        return "missing"
    return str(health.aggregate)


def resolve_notebook_root(corpus: CorpusPaths, notebook_id: str) -> Path:
    """Resolve a notebook id via corpus index, then project-folder scan."""
    nid = notebook_id.strip()
    if not nid:
        raise ValidationError("notebook_id must be non-empty")
    store = CorpusIndexStore(corpus)
    try:
        index = store.load()
    except CorpusError:
        index = None
    if index is not None:
        for entry in index.entries:
            if entry.notebook_id == nid:
                return corpus.resolve_managed(entry.managed_relpath)
    for root in discover_project_roots(corpus.projects_dir):
        try:
            payload_id = (
                ProjectService(
                    open_project_paths(root),
                    clock=SystemClock(),
                    ids=UuidGenerator(),
                )
                .load(reconcile=False)
                .id
            )
        except (TranscribeError, OSError, ValueError, KeyError):
            continue
        if payload_id == nid:
            return root
    raise CorpusError(f"notebook not found: {nid}")


def resolve_notebook_ref(corpus: CorpusPaths, ref: str | Path) -> tuple[str, Path]:
    """Accept a notebook id or project root path; return (notebook_id, root)."""
    text = str(ref).strip()
    if not text:
        raise ValidationError("notebook reference must be non-empty")
    path = Path(text).expanduser()
    if path.exists() and (path / "project.json").exists():
        project = ProjectService(
            open_project_paths(path),
            clock=SystemClock(),
            ids=UuidGenerator(),
        ).load(reconcile=False)
        return project.id, path.resolve()
    root = resolve_notebook_root(corpus, text)
    project = ProjectService(
        open_project_paths(root),
        clock=SystemClock(),
        ids=UuidGenerator(),
    ).load(reconcile=False)
    return project.id, root


def list_candidates(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    include_analysis: bool = False,
) -> list[NotebookCandidate]:
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    out: list[NotebookCandidate] = []
    for root in discover_project_roots(corpus.projects_dir):
        try:
            projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
            project = projects.load(reconcile=False)
        except (TranscribeError, OSError, ValueError, KeyError):
            continue
        total, pending, failed = page_counts(projects, project)
        with_text = pages_with_text_count(projects, project)
        aggregate = "missing"
        if include_analysis:
            try:
                aggregate = analysis_aggregate_for_project(
                    projects, clock=clock, ids=ids
                )
            except (OSError, ValueError, KeyError, TypeError, TranscribeError):
                aggregate = "missing"
        out.append(
            NotebookCandidate(
                notebook_id=project.id,
                title=(project.title or root.name).strip() or root.name,
                root=root,
                managed_relpath=_managed_relpath(corpus, root),
                pages_total=total,
                pages_pending=pending,
                pages_failed=failed,
                pages_with_text=with_text,
                analysis_aggregate=aggregate,
            )
        )
    return out


def select_pending(candidates: list[NotebookCandidate]) -> list[NotebookCandidate]:
    """OCR pending: notebooks with untranscribed or failed pages."""
    return [c for c in candidates if c.pages_pending > 0]


_NEEDS_ANALYSIS = frozenset(
    {"missing", "stale", "failed", "interrupted", "degraded"}
)


def select_needing_analysis(
    candidates: list[NotebookCandidate],
) -> list[NotebookCandidate]:
    """Analyse pending: has effective text and non-healthy aggregate."""
    return [
        c
        for c in candidates
        if c.pages_with_text > 0 and c.analysis_aggregate in _NEEDS_ANALYSIS
    ]


def select_by_ids(
    candidates: list[NotebookCandidate], notebook_ids: list[str]
) -> list[NotebookCandidate]:
    wanted = [n.strip() for n in notebook_ids if n.strip()]
    by_id = {c.notebook_id: c for c in candidates}
    missing = [nid for nid in wanted if nid not in by_id]
    if missing:
        raise CorpusError(f"notebook(s) not found: {', '.join(missing)}")
    return [by_id[nid] for nid in wanted]


def select_from_import_run(
    corpus: CorpusPaths,
    import_run_id: str,
    candidates: list[NotebookCandidate],
    *,
    purpose: str = "transcribe",
) -> list[NotebookCandidate]:
    run = ImportRunStore(corpus).load(import_run_id)
    nids = committed_notebook_ids(run)
    if not nids:
        raise ValidationError(
            f"import run {import_run_id} has no committed notebooks to {purpose}"
        )
    return select_by_ids(candidates, nids)
