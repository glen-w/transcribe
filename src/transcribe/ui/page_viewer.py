"""Canonical page viewer shared by Archive, Search, and Workflow."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.domain.dates import ApproximateDate, normalize_tags
from transcribe.domain.models import Project
from transcribe.errors import TranscribeError
from transcribe.paths import ProjectPaths
from transcribe.services.archive import highlight_terms
from transcribe.services.project import ProjectService
from transcribe.services.thumbnails import ThumbnailService


def _parse_date_input(raw: str) -> ApproximateDate | None:
    text = raw.strip()
    if not text:
        return None
    parts = text.replace("/", "-").split("-")
    try:
        if len(parts) == 1:
            return ApproximateDate(year=int(parts[0]))
        if len(parts) == 2:
            a, b = int(parts[0]), int(parts[1])
            # Accept YYYY-MM or MM-YYYY
            if a > 31:
                return ApproximateDate(year=a, month=b)
            return ApproximateDate(year=b, month=a)
        if len(parts) == 3:
            a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
            if a > 31:  # YYYY-MM-DD
                return ApproximateDate(year=a, month=b, day=c)
            # DD-MM-YYYY
            return ApproximateDate(year=c, month=b, day=a)
    except ValueError as exc:
        raise ValueError(f"Unrecognized date: {raw!r}") from exc
    raise ValueError(f"Unrecognized date: {raw!r}")


def render_page_viewer(
    *,
    paths: ProjectPaths,
    projects: ProjectService,
    project: Project,
    page_id: str,
    page_ids: list[str],
    highlight_query: str = "",
    back_label: str = "Back",
    show_back: bool = True,
) -> Project:
    """Render scan + OCR + metadata for one page; returns possibly updated project."""
    if not page_ids:
        st.info("No pages in this context.")
        return project

    if page_id not in page_ids:
        page_id = page_ids[0]
        st.session_state["view_page_id"] = page_id

    idx = page_ids.index(page_id)
    page = next(p for p in project.pages if p.page_id == page_id)
    render = project.renders[page.active_render_id]
    img_path = paths.resolve_contained(render.image_relpath)
    result = projects.load_page_result(page.page_id)

    top = st.columns([1, 1, 2, 1, 1])
    if show_back:
        if top[0].button(back_label):
            st.session_state.pop("view_page_id", None)
            st.session_state.pop("view_page_ids", None)
            st.session_state.pop("view_highlight", None)
            st.session_state["show_page_viewer"] = False
            return_mode = st.session_state.pop("page_return_mode", None)
            if return_mode:
                st.session_state["ui_mode"] = return_mode
            st.rerun()
    else:
        top[0].write("")
    if top[1].button("Previous", disabled=idx <= 0):
        st.session_state["view_page_id"] = page_ids[idx - 1]
        st.rerun()
    top[2].markdown(
        f"**{project.title}** · page {idx + 1} / {len(page_ids)}"
        + (f" · {page.date.format_display()}" if page.date else " · Undated")
    )
    if top[3].button("Next", disabled=idx >= len(page_ids) - 1):
        st.session_state["view_page_id"] = page_ids[idx + 1]
        st.rerun()
    top[4].caption(f"`{page.page_id[:8]}…`")

    if page.tags:
        st.caption("Tags: " + ", ".join(page.tags))

    left, right = st.columns([3, 2])
    with left:
        st.image(str(img_path), width="stretch")
    with right:
        status = result.status if result else "pending"
        st.write(f"Status: **{status}**")
        attempt = result.active_attempt() if result else None
        raw = attempt.raw_text if attempt else ""
        edited = result.edited_text if result else None
        if edited is not None and attempt and attempt.raw_text is not None:
            st.caption("An edit is active. New OCR raw text is preserved separately.")
            if st.button("Use new transcription"):
                projects.adopt_raw_as_edit(page.page_id)
                st.rerun()
        default_text = edited if edited is not None else (raw or "")
        if highlight_query.strip() and default_text:
            with st.expander("Highlighted transcription", expanded=True):
                st.markdown(highlight_terms(default_text, highlight_query))
        text = st.text_area("Transcription", value=default_text, height=320)
        if st.button("Save edit"):
            projects.save_user_edit(page.page_id, text)
            st.success("Saved")

        st.divider()
        st.caption("Page metadata")
        date_default = page.date.format_display() if page.date else ""
        date_in = st.text_input(
            "Date (YYYY, YYYY-MM, YYYY-MM-DD or DD/MM/YYYY)",
            value=date_default,
            key=f"date_{page.page_id}",
        )
        tags_in = st.text_input(
            "Tags (comma-separated)",
            value=", ".join(page.tags),
            key=f"tags_{page.page_id}",
        )
        if st.button("Save metadata"):
            try:
                new_date = _parse_date_input(date_in)
                project = projects.update_page_metadata(
                    page.page_id,
                    date=new_date,
                    tags=normalize_tags([t for t in tags_in.split(",")]),
                )
                st.success("Metadata saved")
                st.rerun()
            except (ValueError, TranscribeError) as exc:
                st.error(str(exc))

        thumbs = ThumbnailService(paths)
        if st.button("Set as notebook cover"):
            try:
                project = projects.update_notebook_metadata(cover_page_id=page.page_id)
                thumbs.ensure_thumb(project, page.page_id)
                st.success("Cover updated")
            except TranscribeError as exc:
                st.error(str(exc))

    return project


def open_page_context(
    *,
    page_id: str,
    page_ids: list[str],
    project_root: str | Path,
    highlight: str = "",
    return_mode: str | None = None,
) -> None:
    st.session_state["root"] = str(project_root)
    st.session_state["view_page_id"] = page_id
    st.session_state["view_page_ids"] = page_ids
    st.session_state["view_highlight"] = highlight
    st.session_state["show_page_viewer"] = True
    if return_mode:
        st.session_state["page_return_mode"] = return_mode
