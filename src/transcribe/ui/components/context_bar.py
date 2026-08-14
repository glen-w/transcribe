"""Notebook context strip: title plus optional raw path."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.ui.navigation import hide_context_bar, normalize_ui_mode


def render_context_bar(
    *,
    mode: str,
    root: str | None,
    title: str | None,
    show_path: bool = False,
) -> None:
    """Show “Notebook · title” unless this page hides ingest leftover context."""
    if hide_context_bar(normalize_ui_mode(mode)):
        return
    if not root:
        return
    label = (title or "").strip() or Path(str(root)).name
    st.caption(f"Notebook · **{label}**")
    if show_path:
        st.caption(f"`{root}`")
