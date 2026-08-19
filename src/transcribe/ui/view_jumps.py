"""Shared jumps from View consume surfaces into Reading or Review."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.domain.models import Project
from transcribe.ui.action_menus.nav import viewer_page_ids
from transcribe.ui.navigation import apply_destination_to_session
from transcribe.ui.page_viewer import open_page_context


def jump_to_review(
    page_id: str,
    *,
    project: Project,
    project_root: Path | str,
) -> None:
    """Open Review on ``page_id`` with the needs-attention filter set to all pages."""
    page_ids = viewer_page_ids(project)
    if page_id not in page_ids:
        st.toast("That page is no longer in this notebook.")
        return
    root = str(project_root)
    st.session_state["root"] = root
    st.session_state["pending_notebook_root"] = root
    st.session_state["view_page_id"] = page_id
    st.session_state["review_needs_filter"] = "all"
    st.session_state["show_page_viewer"] = False
    st.session_state.pop("page_return_mode", None)
    apply_destination_to_session(st.session_state, "Review")
    st.rerun()


def jump_to_reading(
    page_id: str,
    *,
    project: Project,
    project_root: Path | str,
    return_mode: str,
) -> None:
    """Open Reading on ``page_id``; Back returns to ``return_mode`` (a View page)."""
    page_ids = viewer_page_ids(project)
    if page_id not in page_ids:
        st.toast("That page is no longer in this notebook.")
        return
    open_page_context(
        page_id=page_id,
        page_ids=page_ids,
        project_root=project_root,
        return_mode=return_mode,
    )
    st.session_state["ui_mode"] = "Reading"
    st.rerun()
