"""Session-scoped caches for Streamlit every-rerun hot paths.

Practice rules (aligned with ``corpus_listing_cache``)
-----------------------------------------------------
1. Prefer cheap filesystem tokens (mtimes / archive.generation) over loading
   page-result JSON to decide cache validity.
2. Invalidate on mutations that change the cached answer (Analyse publish,
   Review edits, OCR completion) — do not call ``st.cache_resource.clear()``.
3. Keep helpers Streamlit-UI-only; core services must not import this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from transcribe.domain.models import Project
from transcribe.ui.corpus_listing_cache import get_cached_listing, invalidate_listing_keys
from transcribe.ui.navigation import notebook_has_published_analysis
from transcribe.ui.review_queue import ReviewQueueIndex, build_review_queue_index

# --- Published-analysis nav / View gate ------------------------------------

_PUBLISHED_BY_ROOT_KEY = "tx_nav_published_by_root"
_PUBLISHED_GEN_KEY = "tx_nav_published_gen"


def archive_generation_token(data_dir: Path | str | None) -> str:
    """Cheap workspace mutation token (``data/cache/archive.generation``)."""
    if not data_dir:
        return "0"
    gen_path = Path(data_dir) / "cache" / "archive.generation"
    try:
        return gen_path.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def cached_notebook_has_published_analysis(
    session_state: Any,
    root: Path | str | None,
    *,
    data_dir: Path | str | None = None,
    generation: str | None = None,
) -> bool:
    """Session-cache ``notebook_has_published_analysis`` until archive generation bumps."""
    if not root:
        return False
    gen = generation if generation is not None else archive_generation_token(data_dir)
    if session_state.get(_PUBLISHED_GEN_KEY) != gen:
        session_state[_PUBLISHED_BY_ROOT_KEY] = {}
        session_state[_PUBLISHED_GEN_KEY] = gen
    cache: dict[str, bool] = session_state.setdefault(_PUBLISHED_BY_ROOT_KEY, {})
    key = str(Path(root).expanduser())
    if key not in cache:
        cache[key] = bool(notebook_has_published_analysis(root))
    return bool(cache[key])


def invalidate_published_analysis_cache(session_state: Any, root: Path | str | None = None) -> None:
    """Drop published-analysis answers (one root, or all when ``root`` is None)."""
    if root is None:
        session_state.pop(_PUBLISHED_BY_ROOT_KEY, None)
        session_state.pop(_PUBLISHED_GEN_KEY, None)
        return
    cache = session_state.get(_PUBLISHED_BY_ROOT_KEY)
    if isinstance(cache, dict):
        cache.pop(str(Path(root).expanduser()), None)


# --- Review queue index ----------------------------------------------------

_RW_QUEUE_PREFIX = "tx_rw_queue:"
_RW_REPAIRED_PREFIX = "tx_rw_repaired:"


def review_queue_token(project: Project, *, results_dir: Path) -> str:
    """Cheap Review invalidation: manifest fields + per-page result mtimes."""
    parts: list[str] = [f"n={len(project.pages)}"]
    for page in project.pages:
        date_flag = "1" if (page.date is not None and not page.date_approved) else "0"
        parts.append(
            f"{page.page_id}:{page.review_status or 'unreviewed'}:{date_flag}"
        )
        result_path = results_dir / f"{page.page_id}.json"
        try:
            mtime = result_path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        parts.append(f"r={mtime}")
    return "|".join(parts)


def invalidate_review_queue_cache(session_state: Any, root: Path | str | None = None) -> None:
    """Drop cached Review queue indexes (one notebook or all)."""
    if root is None:
        invalidate_listing_keys(
            session_state,
            *[k for k in list(session_state.keys()) if str(k).startswith(_RW_QUEUE_PREFIX)],
        )
        invalidate_listing_keys(
            session_state,
            *[k for k in list(session_state.keys()) if str(k).startswith(_RW_REPAIRED_PREFIX)],
        )
        return
    key = str(Path(root).expanduser())
    invalidate_listing_keys(
        session_state,
        f"{_RW_QUEUE_PREFIX}{key}",
        f"{_RW_QUEUE_PREFIX}{key}:token",
        f"{_RW_REPAIRED_PREFIX}{key}",
        f"{_RW_REPAIRED_PREFIX}{key}:token",
    )


def get_cached_review_queue_index(
    session_state: Any,
    *,
    root: Path | str,
    project: Project,
    results_dir: Path,
    base_page_ids: Sequence[str],
    load_page_result: Callable[[str], Any],
    repair_page: Callable[[str], Any] | None = None,
) -> ReviewQueueIndex:
    """Return a session-cached Review queue index; repair empty successes on miss."""
    root_key = str(Path(root).expanduser())
    token = review_queue_token(project, results_dir=results_dir)
    cache_key = f"{_RW_QUEUE_PREFIX}{root_key}"
    token_key = f"{cache_key}:token"
    repaired_key = f"{_RW_REPAIRED_PREFIX}{root_key}"
    repaired_token_key = f"{repaired_key}:token"

    if (
        session_state.get(token_key) == token
        and cache_key in session_state
        and isinstance(session_state.get(cache_key), ReviewQueueIndex)
    ):
        return session_state[cache_key]

    if repair_page is not None:
        for page in project.pages:
            try:
                repair_page(page.page_id)
            except Exception:  # noqa: BLE001 — best-effort historical repair
                pass
        # Repair may rewrite result files; retoken so the next click still hits.
        token = review_queue_token(project, results_dir=results_dir)
        session_state[repaired_key] = True
        session_state[repaired_token_key] = token

    index = build_review_queue_index(
        project,
        base_page_ids=base_page_ids,
        load_page_result=load_page_result,
    )
    session_state[cache_key] = index
    session_state[token_key] = token
    return index


def review_repairs_current(session_state: Any, root: Path | str, token: str) -> bool:
    """True when empty-success repair already ran for this Review token."""
    root_key = str(Path(root).expanduser())
    return session_state.get(f"{_RW_REPAIRED_PREFIX}{root_key}:token") == token


# --- View health -----------------------------------------------------------

_VIEW_HEALTH_PREFIX = "tx_view_health:"


def view_health_fs_token(root: Path | str, *, active_run_status: str | None) -> str:
    """Filesystem token for View health (avoids content_revision on cache hit)."""
    root_path = Path(root).expanduser()
    parts: list[str] = [f"run={active_run_status or ''}"]
    try:
        parts.append(f"m={ (root_path / 'project.json').stat().st_mtime_ns }")
    except OSError:
        parts.append("m=0")
    results = root_path / "results"
    if results.is_dir():
        try:
            mtimes = [p.stat().st_mtime_ns for p in results.glob("*.json")]
            parts.append(f"rmax={max(mtimes) if mtimes else 0}")
            parts.append(f"rn={len(mtimes)}")
        except OSError:
            parts.append("rmax=0")
            parts.append("rn=0")
    analysis = root_path / "analysis"
    if analysis.is_dir():
        pub: list[str] = []
        try:
            for child in analysis.iterdir():
                if not child.is_dir() or child.name == "runs":
                    continue
                published = child / "published.json"
                if published.is_file():
                    pub.append(f"{child.name}:{published.stat().st_mtime_ns}")
        except OSError:
            pass
        parts.append("pub=" + ",".join(sorted(pub)))
    return "|".join(parts)


def invalidate_view_health_cache(session_state: Any, root: Path | str | None = None) -> None:
    if root is None:
        for key in list(session_state.keys()):
            if str(key).startswith(_VIEW_HEALTH_PREFIX):
                session_state.pop(key, None)
        return
    root_key = str(Path(root).expanduser())
    invalidate_listing_keys(
        session_state,
        f"{_VIEW_HEALTH_PREFIX}{root_key}",
        f"{_VIEW_HEALTH_PREFIX}{root_key}:token",
    )


def get_cached_view_health(
    session_state: Any,
    *,
    root: Path | str,
    active_run_status: str | None,
    loader: Callable[[], Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Session-cache View health derivation across Overview/Themes/Mood/… hops."""
    root_key = str(Path(root).expanduser())
    token = view_health_fs_token(root, active_run_status=active_run_status)
    return get_cached_listing(
        session_state,
        cache_key=f"{_VIEW_HEALTH_PREFIX}{root_key}",
        token_key=f"{_VIEW_HEALTH_PREFIX}{root_key}:token",
        token=token,
        loader=loader,  # type: ignore[arg-type]
    )


def invalidate_analysis_ui_caches(session_state: Any, root: Path | str | None = None) -> None:
    """Invalidate nav published gate + View health after Analyse publish."""
    invalidate_published_analysis_cache(session_state, root)
    invalidate_view_health_cache(session_state, root)
