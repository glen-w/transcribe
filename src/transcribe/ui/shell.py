"""Streamlit shell: page config and TranscriptX-aligned global styles."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

# Notebooks section
_NOTEBOOK_MODES: tuple[str, ...] = ("View", "Search", "Archive")
# Workflow section
_WORKFLOW_MODES: tuple[str, ...] = ("Transcribe", "Analyse", "Export")
_MODES: tuple[str, ...] = (*_NOTEBOOK_MODES, *_WORKFLOW_MODES)

_LEGACY_MODE_ALIASES: dict[str, str] = {
    "Notebooks": "View",
    "Workflow": "Transcribe",
    # Older Analyse spelling / synonyms
    "Analyze": "Analyse",
    "Run Analysis": "Analyse",
}

_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"


def logo_path() -> Path | None:
    """Packaged brand mark, if present."""
    return _LOGO_PATH if _LOGO_PATH.is_file() else None


def configure_streamlit_page() -> None:
    """``st.set_page_config`` must run before other Streamlit commands."""
    icon: str | Path = logo_path() or "📓"
    st.set_page_config(
        page_title="Transcribe",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def inject_global_styles() -> None:
    """Inject sidebar nav + page chrome CSS (shape/style matched to TranscriptX)."""
    st.markdown(
        """
<style>
    /* Sidebar width — match TranscriptX menu bar density */
    section[data-testid="stSidebar"] {
        min-width: 256px !important;
        max-width: 264px !important;
        width: 260px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
        height: 2rem !important;
        min-height: 2rem !important;
        margin-bottom: 0.15rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 0 !important;
    }
    .tx-sidebar-brand {
        margin: 0 0 0.65rem 0;
        line-height: 1.2;
    }
    .tx-sidebar-brand img {
        display: block;
        width: 100%;
        max-width: 220px;
        height: auto;
        border-radius: 8px;
    }
    .tx-sidebar-brand-text {
        font-size: 1.35rem;
        font-weight: 700;
        color: #1f77b4;
        letter-spacing: 0.01em;
    }
    .tx-sidebar-brand-sub {
        display: block;
        margin-top: 0.35rem;
        margin-bottom: 0.65rem;
        font-size: 0.72rem;
        font-weight: 500;
        color: #8a9ab0;
        letter-spacing: 0.02em;
    }
    section[data-testid="stSidebar"] [data-testid="stImage"] {
        margin: 0 0 0.15rem 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stImage"] img {
        border-radius: 8px;
    }
    section[data-testid="stSidebar"] * {
        overflow-wrap: anywhere;
    }
    /* Global left alignment for main content */
    section[data-testid="stAppViewContainer"] .block-container,
    section[data-testid="stAppViewContainer"] .element-container {
        text-align: left;
    }
    section[data-testid="stAppViewContainer"] .block-container {
        max-width: 1240px;
        margin-left: auto;
        margin-right: auto;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    /* Navigation section headers */
    .nav-section-header,
    .subject-section-header {
        display: block;
        font-size: 0.8rem !important;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #8a9ab0;
        margin: 0.85rem 0 0.15rem 0.1rem !important;
        padding: 0.55rem 0 0.45rem 0 !important;
        line-height: 1.2;
        user-select: none;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:has(.subject-section-header),
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:has(.nav-section-header) {
        margin-top: 0.55rem !important;
        margin-bottom: 0.25rem !important;
        padding-top: 0.15rem !important;
        padding-bottom: 0.15rem !important;
    }
    /* Sidebar nav density */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.35rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] {
        margin: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        min-height: 2.15rem !important;
        height: auto !important;
        line-height: 1.3 !important;
    }
    /* Sidebar nav — solid rounded buttons (readable on dark theme) */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(250, 250, 250, 0.07) !important;
        border: 1px solid rgba(250, 250, 250, 0.14) !important;
        border-radius: 6px !important;
        color: #d7dee8 !important;
        text-align: center;
        padding: 0.35rem 0.55rem;
        font-weight: 500;
        font-size: 0.9rem;
        box-shadow: none !important;
        width: 100%;
        opacity: 1 !important;
        transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
        color: #eef4fb !important;
        background: rgba(31, 119, 180, 0.22) !important;
        border-color: rgba(155, 208, 245, 0.35) !important;
        text-decoration: none;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:focus-visible {
        outline: 2px solid #1f77b4;
        outline-offset: 2px;
        box-shadow: none !important;
    }
    /* Active nav — brighter fill, same size/spacing as inactive */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
        background: rgba(31, 119, 180, 0.38) !important;
        border: 1px solid rgba(155, 208, 245, 0.45) !important;
        border-radius: 6px !important;
        color: #f3f9fd !important;
        text-align: center;
        padding: 0.35rem 0.55rem;
        font-weight: 600;
        font-size: 0.9rem;
        box-shadow: none !important;
        width: 100%;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: rgba(31, 119, 180, 0.48) !important;
        border-color: rgba(155, 208, 245, 0.55) !important;
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]:focus-visible {
        outline: 2px solid #1f77b4;
        outline-offset: 2px;
        box-shadow: none !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button span {
        color: inherit !important;
    }
    /* Page shell title row */
    .tx-page-shell-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #1f77b4;
        margin: 0 0 0.25rem 0;
        line-height: 1.2;
    }
    .tx-page-shell-desc {
        font-size: 0.92rem;
        color: #5a6b7d;
        margin: 0 0 0.75rem 0;
        max-width: 52rem;
    }
</style>
""",
        unsafe_allow_html=True,
    )


def render_brand() -> None:
    """Sidebar brand mark."""
    path = logo_path()
    if path is not None:
        st.image(str(path), width="stretch")
        st.markdown(
            '<span class="tx-sidebar-brand-sub">Notebook OCR</span>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        '<div class="tx-sidebar-brand"><span class="tx-sidebar-brand-text">Transcribe</span>'
        '<span class="tx-sidebar-brand-sub">Notebook OCR</span></div>',
        unsafe_allow_html=True,
    )


def render_nav_section(title: str) -> None:
    """Non-interactive sidebar section label."""
    st.markdown(
        f'<div class="subject-section-header">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def render_page_shell(title: str, description: str | None = None) -> None:
    """Main-area page title matching TranscriptX page shell."""
    st.markdown(
        f'<div class="tx-page-shell-title">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if description:
        st.markdown(
            f'<p class="tx-page-shell-desc">{html.escape(description)}</p>',
            unsafe_allow_html=True,
        )


def set_ui_mode(mode: str) -> None:
    """Switch top-level UI mode and rerun (clears page-viewer overlay)."""
    mode = normalize_ui_mode(mode)
    st.session_state["ui_mode"] = mode
    st.session_state["show_page_viewer"] = False
    st.rerun()


def _nav_button(*, label: str, mode: str, current: str, key_prefix: str = "nav") -> None:
    is_active = current == mode
    text = f"**{label}**" if is_active else label
    btn_type = "primary" if is_active else "secondary"
    kwargs = {
        "key": f"{key_prefix}_{mode}",
        "type": btn_type,
        "width": "stretch",
    }
    if st.button(text, **kwargs):
        if st.session_state.get("ui_mode") != mode:
            set_ui_mode(mode)


def render_mode_nav(current: str) -> str:
    """Left-sidebar mode buttons under Notebooks / Workflow subheads."""
    current = normalize_ui_mode(current)
    st.session_state["ui_mode"] = current

    render_nav_section("Notebooks")
    for mode in _NOTEBOOK_MODES:
        _nav_button(label=mode, mode=mode, current=current, key_prefix="nav")

    render_nav_section("Workflow")
    workflow_labels = {
        "Transcribe": "Transcribe",
        "Analyse": "Analyse",
        "Export": "Export",
    }
    for mode in _WORKFLOW_MODES:
        _nav_button(
            label=workflow_labels[mode],
            mode=mode,
            current=current,
            key_prefix="nav",
        )
    return current


def normalize_ui_mode(raw: str | None) -> str:
    if raw in _LEGACY_MODE_ALIASES:
        return _LEGACY_MODE_ALIASES[raw]
    if raw in _MODES:
        return raw
    return "Archive"


def is_workflow_mode(mode: str) -> bool:
    return normalize_ui_mode(mode) in _WORKFLOW_MODES
