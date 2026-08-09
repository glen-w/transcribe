"""Streamlit shell: page config and TranscriptX-aligned global styles."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

# Notebooks section
_NOTEBOOK_MODES: tuple[str, ...] = ("View", "Search", "Archive")
# Workflow section (import → OCR → review, then analyse / export)
_WORKFLOW_MODES: tuple[str, ...] = (
    "Import",
    "Transcribe",
    "Review",
    "Analyse",
    "Export",
)
# App settings (global prefs, not project OCR settings)
_SETTINGS_MODES: tuple[str, ...] = ("Settings",)
_MODES: tuple[str, ...] = (*_NOTEBOOK_MODES, *_WORKFLOW_MODES, *_SETTINGS_MODES)

_LEGACY_MODE_ALIASES: dict[str, str] = {
    "Notebooks": "View",
    "Workflow": "Import",
    # Former Transcribe sub-tabs
    "Run OCR": "Transcribe",
    "Pages": "Review",
    # Older Analyse spelling / synonyms
    "Analyze": "Analyse",
    "Run Analysis": "Analyse",
}

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_PATH = _ASSETS / "logo.png"
_FAVICON_PATH = _ASSETS / "favicon.png"


def logo_path() -> Path | None:
    """Packaged brand mark, if present."""
    return _LOGO_PATH if _LOGO_PATH.is_file() else None


def favicon_path() -> Path | None:
    """Icon-only mark for browser tab / page icon."""
    if _FAVICON_PATH.is_file():
        return _FAVICON_PATH
    return logo_path()


def configure_streamlit_page() -> None:
    """``st.set_page_config`` must run before other Streamlit commands."""
    icon: str | Path = favicon_path() or "📓"
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
    /* Review modules — compact rows; reveal ✕ on hover / keyboard focus */
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"]) {
        gap: 0.25rem !important;
        align-items: center !important;
        margin: 0 !important;
        padding: 0.05rem 0.2rem;
        border-radius: 0.35rem;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"]):hover {
        background: rgba(120, 130, 145, 0.08);
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"])
        [data-testid="stColumn"] {
        padding: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"])
        [data-testid="stMarkdownContainer"] {
        margin: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"])
        [data-testid="stMarkdownContainer"] p {
        margin: 0 !important;
        line-height: 1.35;
    }
    [class*="st-key-"][class*="_review_rm_"] [data-testid="stButton"] {
        margin: 0 !important;
    }
    [class*="st-key-"][class*="_review_rm_"] [data-testid="stButton"] > button,
    [class*="st-key-"][class*="_review_rm_"] button {
        min-height: unset !important;
        height: 1.5rem !important;
        padding: 0 0.35rem !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        opacity: 0;
        transition: opacity 0.12s ease;
        color: #c9a0a0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"]):hover
        [class*="_review_rm_"] button,
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-"][class*="_review_rm_"]):focus-within
        [class*="_review_rm_"] button,
    [class*="st-key-"][class*="_review_rm_"] button:focus-visible {
        opacity: 1;
    }
    [class*="st-key-"][class*="_review_rm_"] [data-testid="stButton"] > button:hover,
    [class*="st-key-"][class*="_review_rm_"] button:hover {
        color: #e8b4b4 !important;
        background: rgba(180, 90, 90, 0.12) !important;
    }
    /* Compact tertiary action links (Archive / View notebook strips) */
    [class*="st-key-tr_al_"] [data-testid="stButton"] {
        margin: 0 !important;
    }
    [class*="st-key-tr_al_"] [data-testid="stButton"] > button,
    [class*="st-key-tr_al_"] > button {
        min-height: unset !important;
        height: auto !important;
        padding: 0.1rem 0.15rem !important;
        font-size: 0.85rem !important;
        color: #1f77b4 !important;
        gap: 0.28rem !important;
    }
    [class*="st-key-tr_al_"] [data-testid="stButton"] > button span[data-testid="stIconMaterial"],
    [class*="st-key-tr_al_"] [data-testid="stButton"] > button [data-testid="stIconMaterial"],
    [class*="st-key-tr_al_"] > button span[data-testid="stIconMaterial"],
    [class*="st-key-tr_al_"] > button [data-testid="stIconMaterial"] {
        font-size: 0.95rem !important;
        color: inherit !important;
        opacity: 0.9;
    }
    [class*="st-key-tr_al_"] [data-testid="stButton"] > button:hover,
    [class*="st-key-tr_al_"] > button:hover {
        color: #0d5a8c !important;
        text-decoration: underline;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"]) {
        gap: 0 !important;
        justify-content: flex-start !important;
        flex-wrap: wrap;
        align-items: center;
        margin: 0.15rem 0 0.55rem 0;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"])
        [data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: fit-content !important;
        display: flex !important;
        align-items: center;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"])
        [data-testid="stColumn"]:not(:last-child)::after {
        content: "|";
        color: rgba(90, 107, 125, 0.45);
        margin: 0 0.2rem;
        font-size: 0.8rem;
        line-height: 1;
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
        return
    st.markdown(
        '<div class="tx-sidebar-brand"><span class="tx-sidebar-brand-text">Transcribe</span></div>',
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
        # Re-clicking the active mode clears page-viewer overlay (no separate Back).
        if st.session_state.get("ui_mode") != mode or st.session_state.get(
            "show_page_viewer"
        ):
            set_ui_mode(mode)


def render_mode_nav(current: str) -> str:
    """Left-sidebar mode buttons under Notebooks / Workflow subheads."""
    current = normalize_ui_mode(current)
    st.session_state["ui_mode"] = current

    render_nav_section("Notebooks")
    for mode in _NOTEBOOK_MODES:
        _nav_button(label=mode, mode=mode, current=current, key_prefix="nav")

    render_nav_section("Workflow")
    for mode in _WORKFLOW_MODES:
        _nav_button(label=mode, mode=mode, current=current, key_prefix="nav")

    render_nav_section("App")
    for mode in _SETTINGS_MODES:
        _nav_button(label=mode, mode=mode, current=current, key_prefix="nav")
    return current


def normalize_ui_mode(raw: str | None) -> str:
    if raw in _LEGACY_MODE_ALIASES:
        return _LEGACY_MODE_ALIASES[raw]
    if raw in _MODES:
        return raw
    return "Archive"


def is_workflow_mode(mode: str) -> bool:
    return normalize_ui_mode(mode) in _WORKFLOW_MODES
