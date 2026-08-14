"""Per-page content width. Maps and the page viewer need more than Overview."""

from __future__ import annotations

import streamlit as st

from transcribe.ui.navigation import use_wide_layout


def apply_page_width(mode: str) -> None:
    """Relax the default 1240px content cap for wide pages."""
    if not use_wide_layout(mode):
        return
    st.markdown(
        """
<style>
    section[data-testid="stAppViewContainer"] .block-container {
        max-width: min(1680px, 96vw) !important;
    }
</style>
""",
        unsafe_allow_html=True,
    )
