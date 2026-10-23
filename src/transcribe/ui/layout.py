"""Per-page content width. Maps and the page viewer need more than Overview."""

from __future__ import annotations

import streamlit as st

from transcribe.ui.navigation import use_wide_layout


def emit_layout_marker(css_class: str) -> None:
    """Per-run CSS gate so once-injected rules apply only on this page."""
    st.markdown(f'<div class="{css_class}" hidden></div>', unsafe_allow_html=True)


def apply_page_width(mode: str) -> None:
    """Relax the default 1240px content cap for wide pages via a cheap marker."""
    if not use_wide_layout(mode):
        return
    emit_layout_marker("tx-wide-layout")
