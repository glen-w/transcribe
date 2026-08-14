"""View-page wrapper: title → description → flash → status strip → body or empty."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from transcribe.ui.components.empty_state import EmptyCta, EmptyKind, render_empty_state
from transcribe.ui.navigation import PageSpec
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
    body: Callable[[], None] | None = None,
) -> None:
    """TX ``render_run_scoped_page`` analogue. Status strip is always on when given."""
    render_page_shell(spec.title, spec.description)
    if flash:
        st.info(flash)
    if health is not None:
        from transcribe.ui.analysis_health_view import render_status_strip

        render_status_strip(health)
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
