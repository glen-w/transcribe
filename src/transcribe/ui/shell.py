"""Streamlit shell: page config and TranscriptX-aligned global styles."""

from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st

from transcribe.ui.navigation import (
    PRIMARY_MODES,
    SYSTEM_MODES,
    VIEW_MODES,
    WORKFLOW_MODES,
    is_open_notebook_workflow,
    is_workflow_mode,
    nav_disabled_help,
    nav_enabled,
    notebook_has_published_analysis,
    normalize_ui_mode,
    page_spec_for,
)

# Re-export so existing ``from transcribe.ui.shell import normalize_ui_mode`` keeps working.
__all__ = [
    "NOTEBOOK_SELECTOR_KEY",
    "PENDING_NOTEBOOK_ROOT_KEY",
    "SELECTBOX_PLACEHOLDER_NOTEBOOK",
    "configure_streamlit_page",
    "favicon_path",
    "inject_global_styles",
    "is_open_notebook_workflow",
    "is_workflow_mode",
    "logo_path",
    "normalize_ui_mode",
    "render_brand",
    "render_mode_nav",
    "render_nav_section",
    "render_notebook_picker",
    "render_page_shell",
    "set_ui_mode",
    "sync_notebook_selector",
]

NOTEBOOK_SELECTOR_KEY = "notebook_selector"
PENDING_NOTEBOOK_ROOT_KEY = "pending_notebook_root"
SELECTBOX_PLACEHOLDER_NOTEBOOK = "— Select a notebook —"

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
    /* Scope to the action-strip row only. :has(tr_al_) alone also matches
       ancestor grids (Archive notebook columns) and collapses them to
       content-width + wrap. Exclude rows that nest another HorizontalBlock. */
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"]):not(
            :has(> [data-testid="stColumn"] [data-testid="stHorizontalBlock"])
        ) {
        gap: 0 !important;
        justify-content: flex-start !important;
        flex-wrap: wrap;
        align-items: center;
        margin: 0.15rem 0 0.55rem 0;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"]):not(
            :has(> [data-testid="stColumn"] [data-testid="stHorizontalBlock"])
        )
        [data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: fit-content !important;
        display: flex !important;
        align-items: center;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tr_al_"]):not(
            :has(> [data-testid="stColumn"] [data-testid="stHorizontalBlock"])
        )
        [data-testid="stColumn"]:not(:last-child)::after {
        content: "|";
        color: rgba(90, 107, 125, 0.45);
        margin: 0 0.2rem;
        font-size: 0.8rem;
        line-height: 1;
    }
    /* Cover click = Open (transparent button overlays the thumbnail only).
       Require direct-child cover key so ancestor page blocks / sibling
       captions+actions are not part of the hit target or hover outline. */
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_"]) {
        position: relative;
    }
    [class*="st-key-tx_cover_"] {
        position: absolute !important;
        inset: 0 !important;
        z-index: 3;
        margin: 0 !important;
        opacity: 0 !important;
    }
    [class*="st-key-tx_cover_"] [data-testid="stButton"],
    [class*="st-key-tx_cover_"] [data-testid="stButton"] > button,
    [class*="st-key-tx_cover_"] button {
        width: 100% !important;
        height: 100% !important;
        min-height: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        background: transparent !important;
        cursor: pointer !important;
    }
    div[data-testid="stVerticalBlock"]:has(
            > [class*="st-key-tx_cover_"] button:not(:disabled)
        ):hover
        > [data-testid="stImage"]
        img {
        outline: 2px solid rgba(31, 119, 180, 0.5);
        outline-offset: 2px;
        cursor: pointer;
    }
    /* View list: fixed-width cover slot (112×160), contain — no crop.
       Matches VIEW_COVER_WIDTH_PX / chart row in archive_views. */
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-tx_cover_view_"]) {
        align-items: flex-start !important;
    }
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_view_"]) {
        width: 112px !important;
        min-width: 112px !important;
        max-width: 112px !important;
        height: 160px !important;
    }
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_view_"])
        [data-testid="stImage"],
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_view_"])
        [data-testid="stImage"] > div {
        width: 112px !important;
        height: 160px !important;
        display: flex !important;
        align-items: center;
        justify-content: center;
    }
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_view_"])
        [data-testid="stImage"]
        img {
        width: auto !important;
        max-width: 112px !important;
        height: auto !important;
        max-height: 160px !important;
        object-fit: contain !important;
    }
    /* Archive strip: fixed cover height, width follows aspect — no crop.
       Matches ARCHIVE_COVER_HEIGHT_PX in archive_views. */
    div[data-testid="stVerticalBlock"]:has(> [class*="st-key-tx_cover_archive_"])
        [data-testid="stImage"]
        img {
        width: auto !important;
        max-width: 100% !important;
        height: 160px !important;
        max-height: 160px !important;
        object-fit: contain !important;
    }
    /* Run ID info control — custom hover + focus tooltips */
    .tx-run-id-info {
        position: relative;
        display: inline-flex;
        align-items: center;
        vertical-align: middle;
    }
    .tx-run-id-info-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.15rem;
        height: 1.15rem;
        padding: 0;
        margin: 0;
        border: none;
        border-radius: 50%;
        background: transparent;
        color: #8a9ab0;
        font-size: 0.78rem;
        line-height: 1;
        cursor: help;
    }
    .tx-run-id-info-btn:hover,
    .tx-run-id-info-btn:focus {
        color: #1f77b4;
    }
    .tx-run-id-info-btn:focus-visible {
        outline: 2px solid #1f77b4;
        outline-offset: 2px;
    }
    .tx-run-id-info-tip {
        position: absolute;
        left: 50%;
        bottom: calc(100% + 0.35rem);
        transform: translateX(-50%);
        min-width: 10rem;
        max-width: 22rem;
        padding: 0.35rem 0.5rem;
        border-radius: 6px;
        background: #2c3e50;
        color: #f8fafc;
        font-size: 0.72rem;
        line-height: 1.35;
        word-break: break-all;
        white-space: normal;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        z-index: 80;
        transition: opacity 0.12s ease;
    }
    .tx-run-id-info:hover .tx-run-id-info-tip,
    .tx-run-id-info:focus-within .tx-run-id-info-tip,
    .tx-run-id-info-btn:focus + .tx-run-id-info-tip,
    .tx-run-id-info-btn:focus-visible + .tx-run-id-info-tip {
        opacity: 1;
        visibility: visible;
    }
    /* Multi-line methodology / help tips (reuse run-id info control) */
    .tx-methodology-info {
        margin-left: 0.35rem;
    }
    .tx-methodology-info-tip {
        left: 0;
        transform: none;
        bottom: auto;
        top: calc(100% + 0.35rem);
        min-width: 16rem;
        max-width: 28rem;
        padding: 0.5rem 0.65rem;
        word-break: normal;
        overflow-wrap: anywhere;
        text-align: left;
    }
    .tx-trends-heading,
    .tx-section-info-heading {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        margin: 0.75rem 0 0.35rem;
    }
    .tx-trends-heading h4,
    .tx-section-info-heading h4 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
    }
    .tx-caption-with-info {
        font-size: 0.875rem;
        color: var(--text-color);
        opacity: 0.6;
        margin: 0 0 0.35rem 0;
    }
</style>
""",
        unsafe_allow_html=True,
    )


def render_brand() -> None:
    """Sidebar brand mark (HTML img — no Streamlit fullscreen toolbar)."""
    path = logo_path()
    if path is not None:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        st.markdown(
            f'<div class="tx-sidebar-brand">'
            f'<img src="data:image/png;base64,{data}" alt="Transcribe" />'
            f"</div>",
            unsafe_allow_html=True,
        )
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
    raw = mode
    mode = normalize_ui_mode(mode)
    if raw == "Inbox":
        from transcribe.ui.targets import PENDING_IMPORT_TARGET_KEY, TARGET_BATCH

        st.session_state[PENDING_IMPORT_TARGET_KEY] = TARGET_BATCH
    st.session_state["ui_mode"] = mode
    # Clear full viewer nav — not just the overlay flag — so Review cannot
    # resurrect Prev/Next entries for a notebook opened earlier then deleted.
    # Continue-reading map (reading_page_by_root) is preserved across mode changes.
    st.session_state["show_page_viewer"] = False
    st.session_state.pop("view_page_id", None)
    st.session_state.pop("view_page_ids", None)
    st.session_state.pop("view_entries", None)
    st.session_state.pop("view_highlight", None)
    st.session_state.pop("page_return_mode", None)
    st.rerun()


def _nav_button(
    *,
    label: str,
    mode: str,
    current: str,
    key_prefix: str = "nav",
    disabled: bool = False,
    help: str | None = None,
) -> None:
    is_active = current == mode
    text = f"**{label}**" if is_active else label
    btn_type = "primary" if is_active else "secondary"
    # Streamlit keys cannot contain spaces.
    safe = mode.replace(" ", "_")
    kwargs: dict = {
        "key": f"{key_prefix}_{safe}",
        "type": btn_type,
        "width": "stretch",
        "disabled": disabled,
    }
    if help:
        kwargs["help"] = help
    if st.button(text, **kwargs):
        # Re-clicking the active mode clears page-viewer overlay (no separate Back).
        if st.session_state.get("ui_mode") != mode or st.session_state.get("show_page_viewer"):
            set_ui_mode(mode)


def _selectbox_index_kwargs(
    *,
    key: str,
    options: list[str],
    preferred: str | None,
    fallback_index: int = 0,
) -> dict[str, int]:
    """Return ``index=`` only when the widget key is not already in session state."""
    if key in st.session_state:
        current = st.session_state.get(key)
        if current not in options:
            st.session_state[key] = preferred if preferred in options else options[fallback_index]
        return {}
    if preferred and preferred in options:
        return {"index": options.index(preferred)}
    return {"index": fallback_index}


def render_notebook_picker(
    *,
    options: list[tuple[str, str]],
    current_root: str | None,
) -> str | None:
    """TX-style notebook selectbox; return selected root path or None for placeholder.

    ``options`` is ``(root_path, display_title)`` for existing notebooks.
    Selecting a notebook sets workspace context for Workflow pages.
    """
    roots = [root for root, _title in options]
    labels = {root: (title.strip() or Path(root).name) for root, title in options}
    choices = [""] + roots

    # Apply queued external navigation before the widget instantiates.
    if PENDING_NOTEBOOK_ROOT_KEY in st.session_state:
        pending = st.session_state.pop(PENDING_NOTEBOOK_ROOT_KEY)
        if pending == "":
            st.session_state[NOTEBOOK_SELECTOR_KEY] = ""
        else:
            try:
                resolved = str(Path(pending).expanduser().resolve())
            except OSError:
                resolved = pending
            if resolved in choices:
                st.session_state[NOTEBOOK_SELECTOR_KEY] = resolved
            elif pending in choices:
                st.session_state[NOTEBOOK_SELECTOR_KEY] = pending

    preferred: str | None = None
    if current_root:
        try:
            resolved = str(Path(current_root).expanduser().resolve())
        except OSError:
            resolved = current_root
        if resolved in roots:
            preferred = resolved
        elif current_root in roots:
            preferred = current_root
    selected = st.selectbox(
        "Notebook",
        choices,
        format_func=lambda x: (
            SELECTBOX_PLACEHOLDER_NOTEBOOK if x == "" else labels.get(x, Path(x).name)
        ),
        key=NOTEBOOK_SELECTOR_KEY,
        label_visibility="collapsed",
        **_selectbox_index_kwargs(
            key=NOTEBOOK_SELECTOR_KEY,
            options=choices,
            preferred=preferred,
        ),
    )
    return selected if selected else None


def sync_notebook_selector(root: str | None) -> None:
    """Queue sidebar selectbox alignment (safe after the widget has run)."""
    st.session_state[PENDING_NOTEBOOK_ROOT_KEY] = root or ""


def render_mode_nav(
    current: str,
    *,
    notebook_options: list[tuple[str, str]] | None = None,
) -> str:
    """Left-sidebar: unlabeled primary → Workflow → View (picker + pages) → System.

    Stay-don’t-bounce: picker changes never rewrite ``ui_mode``. Missing context
    disables View buttons; the current page stays put.
    """
    current = normalize_ui_mode(current)
    st.session_state["ui_mode"] = current

    for mode in PRIMARY_MODES:
        spec = page_spec_for(mode)
        _nav_button(
            label=spec.nav_label if spec else mode,
            mode=mode,
            current=current,
            key_prefix="nav",
        )

    render_nav_section("Workflow")
    for mode in WORKFLOW_MODES:
        spec = page_spec_for(mode)
        _nav_button(
            label=spec.nav_label if spec else mode,
            mode=mode,
            current=current,
            key_prefix="nav",
        )

    render_nav_section("View")
    opts = list(notebook_options or [])
    if opts:
        previous = st.session_state.get("root")
        selected = render_notebook_picker(
            options=opts,
            current_root=previous,
        )
        if selected:
            st.session_state["root"] = selected
            if selected != previous:
                st.session_state["show_page_viewer"] = False
                st.session_state.pop("view_page_id", None)
                st.session_state.pop("view_page_ids", None)
                st.session_state.pop("view_entries", None)
                st.session_state.pop("view_highlight", None)
        else:
            st.session_state.pop("root", None)
    else:
        st.caption("No notebooks yet — use Workflow → New notebook.")
        st.session_state.pop("root", None)
        sync_notebook_selector(None)

    has_notebook = bool(st.session_state.get("root"))
    has_published = notebook_has_published_analysis(st.session_state.get("root"))
    for mode in VIEW_MODES:
        spec = page_spec_for(mode)
        if spec is None:
            continue
        enabled = nav_enabled(
            spec, has_notebook=has_notebook, has_published=has_published
        )
        # Current page stays reachable even when the picker would disable it.
        disabled = (not enabled) and current != mode
        help_text = None
        if disabled:
            help_text = nav_disabled_help(spec, has_notebook=has_notebook)
        _nav_button(
            label=spec.nav_label,
            mode=mode,
            current=current,
            key_prefix="nav",
            disabled=disabled,
            help=help_text,
        )

    render_nav_section("System")
    for mode in SYSTEM_MODES:
        spec = page_spec_for(mode)
        _nav_button(
            label=spec.nav_label if spec else mode,
            mode=mode,
            current=current,
            key_prefix="nav",
        )
    return current
