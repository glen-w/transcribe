"""Thumbnails overview for Reading and Review page surfaces.

Toggle replaces the single-page scan with a grid of page thumbs. Each thumb has
a page button underneath — click it (or **Go to page** in the info panel) to
leave the grid and open that page. The right panel shows info for the page that
was current when entering the grid.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.domain.models import PageIndex, Project
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.paths import ProjectPaths
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
from transcribe.ui import icons as ic
from transcribe.ui.components.info_tooltip import widget_help

_THUMBS_MODE_KEY = "viewer_thumbs_mode"
_THUMBS_COLS_KEY = "viewer_thumbs_cols"
_THUMBS_SELECTED_KEY = "viewer_thumbs_selected"

_MIN_COLS = 3
_MAX_COLS = 8
_DEFAULT_COLS = 5


def thumbs_mode_active() -> bool:
    return bool(st.session_state.get(_THUMBS_MODE_KEY))


def clear_thumbs_view_state(session: dict | None = None) -> None:
    state = session if session is not None else st.session_state
    state.pop(_THUMBS_MODE_KEY, None)
    state.pop(_THUMBS_COLS_KEY, None)
    state.pop(_THUMBS_SELECTED_KEY, None)


def _cols() -> int:
    raw = st.session_state.get(_THUMBS_COLS_KEY, _DEFAULT_COLS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = _DEFAULT_COLS
    return min(max(n, _MIN_COLS), _MAX_COLS)


def _selected_page_id(fallback: str) -> str:
    selected = st.session_state.get(_THUMBS_SELECTED_KEY)
    if isinstance(selected, str) and selected.strip():
        return selected
    return fallback


def render_thumbs_toggle_button(*, key: str) -> None:
    """Icon button that enters or leaves the thumbnails overview."""
    active = thumbs_mode_active()
    label = "Page view" if active else "Thumbnails"
    help_text = (
        "Return to the single-page view"
        if active
        else "Browse pages as a thumbnail grid"
    )
    if st.button(
        label,
        key=key,
        help=widget_help(help_text),
        icon=ic.GRID_VIEW,
        type="secondary" if active else "tertiary",
        width="stretch",
    ):
        if active:
            st.session_state[_THUMBS_MODE_KEY] = False
        else:
            st.session_state[_THUMBS_MODE_KEY] = True
            current = st.session_state.get("view_page_id")
            if isinstance(current, str) and current:
                st.session_state[_THUMBS_SELECTED_KEY] = current
        st.rerun()


def _entry_for_page(
    entries: list[dict[str, str]], page_id: str
) -> dict[str, str] | None:
    for entry in entries:
        if entry.get("page_id") == page_id:
            return entry
    return None


def _notebook_cache(
    entries: list[dict[str, str]],
) -> dict[str, tuple[ProjectPaths, ProjectService, Project]]:
    """Load each distinct project root once for the grid."""
    cache: dict[str, tuple[ProjectPaths, ProjectService, Project]] = {}
    roots = {str(e.get("project_root") or "") for e in entries}
    for root in roots:
        if not root:
            continue
        try:
            paths = open_project_paths(Path(root))
            projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
            project = projects.load(reconcile=False)
        except Exception:  # noqa: BLE001
            continue
        cache[root] = (paths, projects, project)
    return cache


def _page_from_cache(
    cache: dict[str, tuple[ProjectPaths, ProjectService, Project]],
    entry: dict[str, str],
) -> tuple[ProjectPaths, ProjectService, Project, PageIndex] | None:
    root = str(entry.get("project_root") or "")
    page_id = str(entry.get("page_id") or "")
    bundle = cache.get(root)
    if bundle is None or not page_id:
        return None
    paths, projects, project = bundle
    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        return None
    return paths, projects, project, page


def _warm_grid_thumbs(
    entries: list[dict[str, str]],
    cache: dict[str, tuple[ProjectPaths, ProjectService, Project]],
) -> None:
    """Ensure small grid JPEGs exist before painting the grid (one pass)."""
    by_root: dict[str, list[str]] = {}
    for entry in entries:
        root = str(entry.get("project_root") or "")
        page_id = str(entry.get("page_id") or "")
        if not root or not page_id or root not in cache:
            continue
        by_root.setdefault(root, []).append(page_id)
    for root, page_ids in by_root.items():
        paths, _projects, project = cache[root]
        ThumbnailService(paths).ensure_thumbs_for_pages(
            project,
            page_ids,
            cover=False,
            grid=True,
        )


def _open_entry(entry: dict[str, str]) -> None:
    """Leave thumbs mode and open the page in the normal viewer."""
    # Lazy import: page_viewer imports this module for the toggle.
    from transcribe.ui.page_viewer import _navigate_to_entry, remember_reading_page

    page_id = entry["page_id"]
    root = str(entry.get("project_root") or "")
    st.session_state[_THUMBS_MODE_KEY] = False
    st.session_state[_THUMBS_SELECTED_KEY] = page_id
    _navigate_to_entry(entry)
    remember_reading_page(root, page_id)


def _open_entry_click(page_id: str, project_root: str) -> None:
    """``on_click`` adapter (args must be primitives for Streamlit callbacks)."""
    _open_entry({"page_id": page_id, "project_root": project_root})


def _render_zoom_controls(*, key_prefix: str) -> None:
    cols_n = _cols()
    zoom_out, label, zoom_in = st.columns([1, 2, 1])
    with zoom_out:
        if st.button(
            "",
            key=f"{key_prefix}_zoom_out",
            help=widget_help("Show more thumbnails (smaller)"),
            icon=ic.ZOOM_OUT,
            type="tertiary",
            disabled=cols_n >= _MAX_COLS,
        ):
            st.session_state[_THUMBS_COLS_KEY] = cols_n + 1
            st.rerun()
    with label:
        st.caption(f"{cols_n} across")
    with zoom_in:
        if st.button(
            "",
            key=f"{key_prefix}_zoom_in",
            help=widget_help("Show fewer thumbnails (larger)"),
            icon=ic.ZOOM_IN,
            type="tertiary",
            disabled=cols_n <= _MIN_COLS,
        ):
            st.session_state[_THUMBS_COLS_KEY] = cols_n - 1
            st.rerun()


def _render_thumb_cell(
    *,
    entry: dict[str, str],
    index: int,
    selected_id: str,
    key_prefix: str,
    cache: dict[str, tuple[ProjectPaths, ProjectService, Project]],
) -> None:
    page_id = entry["page_id"]
    root = str(entry.get("project_root") or "")
    loaded = _page_from_cache(cache, entry)
    selected = page_id == selected_id
    # Visible full-width control under the image — Streamlit cannot attach
    # on_click to st.image, and CSS overlays over images are unreliable in
    # column grids. on_click mutates session before the next run (no mid-render rerun).
    open_key = f"tx_grid_open_{key_prefix}_{page_id[:12]}_{index}"
    with st.container(border=selected):
        if loaded is None:
            st.caption("(missing)")
            label = f"p.{index + 1}"
        else:
            paths, _projects, project, page = loaded
            thumbs = ThumbnailService(paths)
            thumb = thumbs.ensure_grid_thumb(project, page_id)
            if thumb is not None and thumb.exists():
                st.image(str(thumb), width="stretch")
            else:
                st.caption("(no image)")
            date_bit = page.date.format_display() if page.date else "Undated"
            label = f"p.{index + 1} · {date_bit}"
        st.button(
            label,
            key=open_key,
            type="primary" if selected else "secondary",
            width="stretch",
            help=widget_help("Open this page in the normal view"),
            on_click=_open_entry_click,
            args=(page_id, root),
        )


def _cover_page_id(project: Project) -> str | None:
    return project.cover_page_id or (project.pages[0].page_id if project.pages else None)


def _render_page_info_panel(
    *,
    entries: list[dict[str, str]],
    selected_id: str,
    key_prefix: str,
    cache: dict[str, tuple[ProjectPaths, ProjectService, Project]],
) -> None:
    entry = _entry_for_page(entries, selected_id)
    if entry is None and entries:
        entry = entries[0]
        selected_id = entry["page_id"]
        st.session_state[_THUMBS_SELECTED_KEY] = selected_id
    if entry is None:
        st.info("No pages in this view.")
        return

    loaded = _page_from_cache(cache, entry)
    if loaded is None:
        st.warning("Could not load this page.")
        return
    paths, projects, project, page = loaded
    result = projects.load_page_result(page.page_id)
    idx = next(
        (i for i, e in enumerate(entries) if e.get("page_id") == page.page_id),
        0,
    )
    date_label = page.date.format_display() if page.date else "Undated"
    if page.date is not None and not page.date_approved:
        date_label = f"{date_label} (suggested)"
    status = result.status if result else "pending"
    review = (page.review_status or "unreviewed").replace("_", " ")

    st.markdown(f"**{project.title}**")
    st.write(f"Page **{idx + 1}** of {len(entries)}")
    st.caption(f"`{page.page_id[:8]}…`")
    st.write(f"Date: **{date_label}**")
    st.write(f"OCR: **{status}** · Review: **{review}**")
    if page.ignored:
        st.caption("Ignored in Reader by default.")
    if page.tags:
        from transcribe.services.tags import TagService
        from transcribe.ui.tag_pills import render_tag_chips

        catalog = TagService().load_catalog()
        render_tag_chips(page.tags, catalog)

    try:
        from transcribe.ui.page_metrics_view import (
            ensure_page_metrics,
            render_page_metrics_strip,
        )

        if page.page_id != _cover_page_id(project):
            metrics_doc = ensure_page_metrics(projects, project)
            row = metrics_doc.row_for_page(page.page_id) if metrics_doc else None
            render_page_metrics_strip(row)
    except Exception:  # noqa: BLE001
        pass

    text = (result.effective_text() if result else None) or ""
    preview = " ".join(text.split())
    if preview:
        if len(preview) > 480:
            preview = preview[:477] + "…"
        st.markdown("#### Transcription")
        st.markdown(escape_markdown_plain(preview))
    else:
        st.caption("No transcription text on this page.")

    st.button(
        "Go to page",
        key=f"{key_prefix}_go",
        type="primary",
        width="stretch",
        icon=ic.ARROW_FORWARD,
        help=widget_help("Open this page in the normal view"),
        on_click=_open_entry_click,
        args=(entry["page_id"], str(entry.get("project_root") or "")),
    )


def render_thumbnails_view(
    *,
    entries: list[dict[str, str]],
    current_page_id: str,
    key_prefix: str = "thumbs",
) -> None:
    """Full thumbnails overview: grid on the left, page info on the right."""
    if not entries:
        st.info("No pages in this view.")
        return

    selected = _selected_page_id(current_page_id)
    if _entry_for_page(entries, selected) is None:
        selected = entries[0]["page_id"]
        st.session_state[_THUMBS_SELECTED_KEY] = selected

    cache = _notebook_cache(entries)
    _warm_grid_thumbs(entries, cache)

    toolbar, _ = st.columns([2, 5])
    with toolbar:
        _render_zoom_controls(key_prefix=key_prefix)

    left, right = st.columns([3, 2], gap="medium")
    cols_n = _cols()
    with left:
        rows = (len(entries) + cols_n - 1) // cols_n
        for row_i in range(rows):
            cells = st.columns(cols_n, gap="small")
            for col_i, cell in enumerate(cells):
                idx = row_i * cols_n + col_i
                if idx >= len(entries):
                    break
                with cell:
                    _render_thumb_cell(
                        entry=entries[idx],
                        index=idx,
                        selected_id=selected,
                        key_prefix=key_prefix,
                        cache=cache,
                    )
    with right:
        _render_page_info_panel(
            entries=entries,
            selected_id=selected,
            key_prefix=key_prefix,
            cache=cache,
        )
