"""View-page wrapper: title → description → flash → status strip → body or empty."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from transcribe.ui.components.empty_state import EmptyCta, EmptyKind, render_empty_state
from transcribe.ui.navigation import (
    VIEW_PAGE_PANELS,
    VIEW_PANEL_PENDING_KEY,
    PageSpec,
    ViewPanel,
)
from transcribe.ui.shell import render_page_shell, set_ui_mode


def render_analyse_cta(*, key: str = "view_analyse_cta") -> None:
    """Fixed Analyse CTA (not a configurable action-menu row)."""

    def _go() -> None:
        set_ui_mode("Analyse")

    render_empty_state(
        kind="no_results_yet",
        title="No published analysis yet",
        body="Run Analyse on this notebook to fill this page.",
        primary=EmptyCta(
            label="Analyse this notebook",
            on_click=_go,
            key=key,
            primary=True,
        ),
    )


def view_panel_widget_key(page_id: str, project_id: str) -> str:
    safe = page_id.replace(" ", "_").lower()
    return f"view_panel_{safe}_{project_id}"


def select_view_panel(
    page_id: str,
    *,
    project_id: str,
    render: bool = True,
) -> ViewPanel | None:
    """Apply a pending alias and optionally render the in-page section control."""
    panels = VIEW_PAGE_PANELS.get(page_id)
    if not panels:
        return None
    key = view_panel_widget_key(page_id, project_id)
    ids = tuple(panel.id for panel in panels)
    labels = {panel.id: panel.label for panel in panels}
    pending = st.session_state.pop(VIEW_PANEL_PENDING_KEY, None)
    if pending in ids:
        st.session_state[key] = pending
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]
    selected = st.session_state.get(key, ids[0])
    if render:
        chosen = st.segmented_control(
            "Section",
            options=list(ids),
            format_func=lambda i: labels[i],
            key=key,
            label_visibility="collapsed",
            required=True,
            width="stretch",
        )
        if chosen is not None:
            selected = chosen
    if selected not in ids:
        selected = ids[0]
    return next(panel for panel in panels if panel.id == selected)


def render_notebook_view_page(
    spec: PageSpec,
    *,
    flash: str | None = None,
    health: Any | None = None,
    empty_kind: EmptyKind | None = None,
    empty_title: str | None = None,
    empty_body: str | None = None,
    show_analyse_cta: bool = False,
    analyse_cta_key: str = "view_analyse_cta",
    ask_note: bool = False,
    body: Callable[[], None] | None = None,
) -> None:
    """TX ``render_run_scoped_page`` analogue. Status strip is always on when given."""
    render_page_shell(spec.title, spec.description)
    if flash:
        st.info(flash)
    if health is not None:
        from transcribe.ui.analysis_health_view import render_status_strip

        render_status_strip(health, ask_note=ask_note)
    if empty_kind is not None:
        primary = None
        if show_analyse_cta:

            def _go() -> None:
                set_ui_mode("Analyse")

            primary = EmptyCta(
                label="Analyse this notebook",
                on_click=_go,
                key=analyse_cta_key,
                primary=True,
            )
        render_empty_state(
            kind=empty_kind,
            title=empty_title or "Nothing to show",
            body=empty_body or "",
            primary=primary,
        )
        return
    if show_analyse_cta and body is None:
        render_analyse_cta(key=analyse_cta_key)
        return
    if body is not None:
        body()
