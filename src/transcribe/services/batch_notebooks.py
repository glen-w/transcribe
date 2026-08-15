"""Shared multi-notebook candidate discovery for bulk OCR / Analyse."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from transcribe.corpus.import_run import ImportRunStore, committed_notebook_ids
from transcribe.corpus.index import CorpusIndexStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, TranscribeError, ValidationError
from transcribe.ports import Clock, IdGenerator, SystemClock, UuidGenerator
from transcribe.services.archive import discover_project_roots
from transcribe.services.project import ProjectService, open_project_paths

# Mirror analysis.health degraded capabilities without importing the runner stack.
_DEGRADED_CAPABILITIES = frozenset(
    {
        "unavailable_model",
        "unavailable_extra",
        "unavailable_dependency",
        "insufficient_data",
        "skipped_not_applicable",
    }
)
_DEGRADED_OUTCOMES = frozenset(
    {
        "unavailable_dependency",
        "insufficient_data",
        "skipped_not_applicable",
    }
)


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
    total, pending, failed, _with_text, _results = collect_page_stats(projects, project)
    return total, pending, failed


def pages_with_text_count(projects: ProjectService, project) -> int:
    _total, _pending, _failed, with_text, _results = collect_page_stats(projects, project)
    return with_text


def page_stats(projects: ProjectService, project) -> tuple[int, int, int, int]:
    """Single pass over page results → (total, pending_or_failed, failed, with_text)."""
    total, pending, failed, with_text, _results = collect_page_stats(projects, project)
    return total, pending, failed, with_text


def collect_page_stats(
    projects: ProjectService, project
) -> tuple[int, int, int, int, dict[str, Any]]:
    """Load each page result once → counts plus ``{page_id: result}``."""
    total = len(project.pages)
    pending = 0
    failed = 0
    with_text = 0
    results: dict[str, Any] = {}
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        results[page.page_id] = result
        if result is None or result.status != "succeeded":
            pending += 1
        if result is not None and result.status == "failed":
            failed += 1
        text = result.effective_text() if result else None
        if text and str(text).strip():
            with_text += 1
    return total, pending, failed, with_text, results


def enrich_page_stats(
    candidates: list[NotebookCandidate],
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> list[NotebookCandidate]:
    """Fill pending/text counts for a small candidate list (import-run captions)."""
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    out: list[NotebookCandidate] = []
    for cand in candidates:
        try:
            projects = ProjectService(open_project_paths(cand.root), clock=clock, ids=ids)
            project = projects.load(reconcile=False)
            total, pending, failed, with_text, _results = collect_page_stats(
                projects, project
            )
        except (TranscribeError, OSError, ValueError, KeyError):
            out.append(cand)
            continue
        out.append(
            replace(
                cand,
                pages_total=total,
                pages_pending=pending,
                pages_failed=failed,
                pages_with_text=with_text,
            )
        )
    return out


def _fingerprint_for_module(
    module_id: str,
    *,
    projects: ProjectService,
    project,
    page_fp: list[str | None],
    para_fp: list[str | None],
    results: dict[str, Any] | None = None,
) -> str | None:
    """Lazy page/paragraph content fingerprints for scan-time staleness."""
    from transcribe.analysis.adapter import (
        build_page_v1_document,
        build_paragraph_v1_document,
    )
    from transcribe.analysis.document import (
        AnalysisDocumentError,
        content_fingerprint,
    )
    from transcribe.analysis.runner import PARAGRAPH_PREFERRED

    try:
        if module_id in PARAGRAPH_PREFERRED:
            if para_fp[0] is None:
                try:
                    doc = build_paragraph_v1_document(
                        project, projects, results=results
                    )
                except AnalysisDocumentError:
                    doc = build_page_v1_document(project, projects, results=results)
                para_fp[0] = content_fingerprint(doc)
            return para_fp[0]
        if page_fp[0] is None:
            page_fp[0] = content_fingerprint(
                build_page_v1_document(project, projects, results=results)
            )
        return page_fp[0]
    except AnalysisDocumentError:
        return None


def _latest_run_status(runs_dir) -> str | None:
    """Newest analysis run record status, if any (scan path; no full history walk)."""
    try:
        files = list(runs_dir.glob("*.json"))
    except OSError:
        return None
    if not files:
        return None
    newest = files[0]
    newest_mtime = -1
    for path in files:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            continue
        if mtime >= newest_mtime:
            newest = path
            newest_mtime = mtime
    try:
        from transcribe.persistence.atomic import read_json

        payload = read_json(newest)
    except (OSError, ValueError, TypeError):
        return None
    status = str(payload.get("status") or "")
    return status or None


def analysis_aggregate_for_project(
    projects: ProjectService,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    project=None,
    results: dict[str, Any] | None = None,
    registered: dict | None = None,
) -> str:
    """Corpus-scan aggregate for candidate captions / needing-analysis filter.

    Avoids ``planned_cache_identity`` and Ollama binding (those make batch
    discovery hang when many notebooks have published LLM modules). Uses
    published envelopes + content fingerprints + registered module versions.
    View status strips still use full ``derive_analysis_health``.
    """
    _ = clock
    _ = ids
    from transcribe.analysis.modules import get_registered_modules
    from transcribe.analysis.storage import AnalysisStorage, RUNS_DIR_NAME
    from transcribe.persistence.locks import analysis_lock_held

    analysis_dir = projects.paths.analysis_dir
    if not analysis_dir.is_dir():
        return "missing"

    if analysis_lock_held(projects.paths.analysis_lock):
        return "running"

    module_ids = sorted(
        p.name
        for p in analysis_dir.iterdir()
        if p.is_dir()
        and p.name != RUNS_DIR_NAME
        and (p / "published.json").is_file()
    )
    if not module_ids:
        return "missing"

    storage = AnalysisStorage(projects.paths)
    latest_status = _latest_run_status(storage.runs_dir())
    if latest_status == "interrupted":
        return "interrupted"
    if latest_status == "running":
        return "running"

    if project is None:
        try:
            project = projects.load(reconcile=False)
        except (TranscribeError, OSError, ValueError, KeyError):
            return "missing"

    modules = registered if registered is not None else get_registered_modules()
    page_fp: list[str | None] = [None]
    para_fp: list[str | None] = [None]
    saw_ok = False
    saw_failed = False
    saw_degraded = False

    for mid in module_ids:
        published = storage.read_published(mid)
        if published is None:
            continue
        module = modules.get(mid)
        if module is not None and published.get("module_version") != module.module_version:
            return "stale"
        expected_fp = _fingerprint_for_module(
            mid,
            projects=projects,
            project=project,
            page_fp=page_fp,
            para_fp=para_fp,
            results=results,
        )
        if expected_fp is None or published.get("content_fingerprint") != expected_fp:
            return "stale"
        outcome = str(published.get("outcome") or "")
        capability = str(published.get("capability") or "")
        if outcome == "failed" or capability == "failed":
            saw_failed = True
            continue
        if capability in _DEGRADED_CAPABILITIES or outcome in _DEGRADED_OUTCOMES:
            saw_degraded = True
            continue
        saw_ok = True

    if saw_failed:
        return "failed"
    if not saw_ok and not saw_degraded:
        return "missing"
    if saw_degraded:
        return "degraded"
    return "healthy"


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
    include_page_stats: bool = True,
) -> list[NotebookCandidate]:
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    registered = None
    if include_analysis:
        from transcribe.analysis.modules import get_registered_modules

        registered = get_registered_modules()
    out: list[NotebookCandidate] = []
    for root in discover_project_roots(corpus.projects_dir):
        try:
            projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
            project = projects.load(reconcile=False)
        except (TranscribeError, OSError, ValueError, KeyError):
            continue
        total = len(project.pages)
        pending = failed = with_text = 0
        aggregate = "missing"
        results_map: dict[str, Any] | None = None
        if include_page_stats:
            total, pending, failed, with_text, results_map = collect_page_stats(
                projects, project
            )
        if include_analysis:
            # Empty-text notebooks never enter needing-analysis; skip health I/O.
            if with_text == 0 and include_page_stats:
                aggregate = "missing"
            else:
                try:
                    aggregate = analysis_aggregate_for_project(
                        projects,
                        clock=clock,
                        ids=ids,
                        project=project,
                        results=results_map,
                        registered=registered,
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


def list_candidates_light(
    corpus: CorpusPaths,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> list[NotebookCandidate]:
    """Identity + title for pickers. Skips page-result and analysis I/O."""
    return list_candidates(
        corpus,
        clock=clock,
        ids=ids,
        include_analysis=False,
        include_page_stats=False,
    )


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
