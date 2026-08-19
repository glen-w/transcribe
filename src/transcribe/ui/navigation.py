"""PageSpec backbone: sidebar IA, mode aliases, and stay-don’t-bounce gating."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, MutableMapping

RequiredContext = Literal["none", "notebook", "notebook_published"]
NavSection = Literal["primary", "workflow", "view", "system"]
AllowedFallback = Literal["stay"]

# Detection storage is independent of analysis published.json.
_RUNS_DIR_NAME = "runs"


@dataclass(frozen=True)
class PageSpec:
    """One top-level UI page (sidebar button + page-shell copy)."""

    id: str
    nav_label: str
    title: str
    description: str
    section: NavSection
    required_context: RequiredContext
    allowed_fallback: AllowedFallback = "stay"


PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec(
        id="Home",
        nav_label="Home",
        title="Home",
        description="Create a notebook, check Ollama, and jump back into recent work.",
        section="primary",
        required_context="none",
    ),
    PageSpec(
        id="Library",
        nav_label="Library",
        title="Library",
        description="Browse notebook covers and jump into Reading or a workflow.",
        section="primary",
        required_context="none",
    ),
    PageSpec(
        id="Search",
        nav_label="Search",
        title="Search",
        description="Find text across transcribed notebook pages.",
        section="primary",
        required_context="none",
    ),
    PageSpec(
        id="Archive",
        nav_label="Archive",
        title="Archive",
        description="Browse notebooks by timeline, tags, and recent activity.",
        section="primary",
        required_context="none",
    ),
    PageSpec(
        id="Places",
        nav_label="Places",
        title="Places",
        description="Map places mentioned across all notebooks (from published NER).",
        section="primary",
        required_context="none",
    ),
    PageSpec(
        id="New notebook",
        nav_label="New notebook",
        title="New notebook",
        description="Create a notebook, then import pages and run OCR.",
        section="workflow",
        required_context="none",
    ),
    PageSpec(
        id="Import",
        nav_label="Import",
        title="Import",
        description="Add pages to this notebook, or batch-import folders into the corpus.",
        section="workflow",
        required_context="none",
    ),
    PageSpec(
        id="Transcribe",
        nav_label="Transcribe",
        title="Transcribe",
        description="Configure Ollama and run OCR on this notebook or many notebooks.",
        section="workflow",
        required_context="none",
    ),
    PageSpec(
        id="Review",
        nav_label="Review",
        title="Review",
        description="Correct pages that need attention — dates, empty text, failed OCR.",
        section="workflow",
        required_context="notebook",
    ),
    PageSpec(
        id="Analyse",
        nav_label="Analyse",
        title="Analyse",
        description="This notebook or Batch: same Analyse plan across many notebooks.",
        section="workflow",
        required_context="none",
    ),
    PageSpec(
        id="Detect",
        nav_label="Detect",
        title="Detect",
        description=(
            "Scan notebook pages for poetry, lists, to-dos, quotations, beer labels, "
            "and custom phenomena."
        ),
        section="workflow",
        required_context="notebook",
    ),
    PageSpec(
        id="Export",
        nav_label="Export",
        title="Export",
        description="Export notebook JSON, Markdown, plain text, HTML, EPUB, and PDF.",
        section="workflow",
        required_context="notebook",
    ),
    PageSpec(
        id="Reading",
        nav_label="Read",
        title="Reading",
        description="Read pages chronologically without editing.",
        section="view",
        required_context="notebook",
    ),
    PageSpec(
        id="Overview",
        nav_label="Overview",
        title="Overview",
        description="Notebook snapshot: counts, diversity, entities, themes, and page ink.",
        section="view",
        required_context="notebook",
    ),
    PageSpec(
        id="Summaries",
        nav_label="Summaries",
        title="Summaries",
        description="Highlights, summary, and insights for this notebook.",
        section="view",
        required_context="notebook",
    ),
    PageSpec(
        id="Ask",
        nav_label="Ask",
        title="Ask notebook",
        description=(
            "Ask a question grounded in this notebook. Ad-hoc Ask does not update batch health."
        ),
        section="view",
        required_context="notebook",
    ),
    PageSpec(
        id="Themes",
        nav_label="Themes",
        title="Themes",
        description="Topics, people, and places in this notebook.",
        section="view",
        required_context="notebook_published",
    ),
    PageSpec(
        id="Mood",
        nav_label="Mood",
        title="Mood & tone",
        description="Emotion, affect tension, hedging, and salient quotes.",
        section="view",
        required_context="notebook_published",
    ),
    PageSpec(
        id="Settings",
        nav_label="Settings",
        title="Settings",
        description="Workspace knobs: analysis presets, models, profiles, and interface menus.",
        section="system",
        required_context="none",
    ),
    PageSpec(
        id="Diagnostics",
        nav_label="Diagnostics",
        title="Diagnostics",
        description="Workspace doctor, optional notebook doctor, and Ollama reachability.",
        section="system",
        required_context="none",
    ),
)

PAGE_SPECS_BY_ID: dict[str, PageSpec] = {spec.id: spec for spec in PAGE_SPECS}
PAGE_IDS: tuple[str, ...] = tuple(spec.id for spec in PAGE_SPECS)

PRIMARY_MODES: tuple[str, ...] = tuple(s.id for s in PAGE_SPECS if s.section == "primary")
WORKFLOW_MODES: tuple[str, ...] = tuple(s.id for s in PAGE_SPECS if s.section == "workflow")
VIEW_MODES: tuple[str, ...] = tuple(s.id for s in PAGE_SPECS if s.section == "view")
SYSTEM_MODES: tuple[str, ...] = tuple(s.id for s in PAGE_SPECS if s.section == "system")

# Modes that hide the notebook context bar (ingest launchers + Home + System).
CONTEXT_BAR_HIDDEN_MODES: frozenset[str] = frozenset(
    {
        "Home",
        "New notebook",
        "Import",
        "Transcribe",
        "Analyse",
        "Settings",
        "Diagnostics",
    }
)

# Maps and the page viewer need width more than Overview.
# Themes hosts the this-notebook People & places map.
WIDE_LAYOUT_MODES: frozenset[str] = frozenset(
    {"Home", "Reading", "Review", "Archive", "Places", "Themes"}
)

_LEGACY_MODE_ALIASES: dict[str, str] = {
    "Notebooks": "Library",
    "View": "Library",
    "Workflow": "Import",
    "Create": "New notebook",
    "New": "New notebook",
    "Run OCR": "Transcribe",
    "Pages": "Review",
    "Analyze": "Analyse",
    "Run Analysis": "Analyse",
    "Published results": "Overview",
    "Inbox": "Import",
    "App": "Settings",
    "Moments": "Mood",
    "People": "Themes",
}

VIEW_PANEL_PENDING_KEY = "view_panel_pending"


@dataclass(frozen=True)
class ViewPanel:
    """In-page section on a merged View consume page."""

    id: str
    label: str
    title: str
    description: str


VIEW_PAGE_PANELS: dict[str, tuple[ViewPanel, ...]] = {
    "Themes": (
        ViewPanel(
            "themes",
            "Themes",
            "Themes",
            "Topics, keyphrases, and how themes shift across the notebook.",
        ),
        ViewPanel(
            "people",
            "People",
            "People & places",
            "People and places from published NER for this notebook.",
        ),
    ),
    "Mood": (
        ViewPanel(
            "mood",
            "Mood",
            "Mood & tone",
            "Emotion, affect tension, and hedging across the notebook.",
        ),
        ViewPanel(
            "moments",
            "Moments",
            "Moments",
            "Salient quotes from the notebook.",
        ),
    ),
}

# Former top-level View pages that now open a parent page + in-page section.
_VIEW_PANEL_ALIASES: dict[str, tuple[str, str]] = {
    "Moments": ("Mood", "moments"),
    "People": ("Themes", "people"),
}

NAV_HELP_SELECT_NOTEBOOK = "Select a notebook"
NAV_HELP_ANALYSE_FIRST = "Analyse this notebook first"


def page_spec_for(mode: str) -> PageSpec | None:
    return PAGE_SPECS_BY_ID.get(normalize_ui_mode(mode) if mode else "")


def notebook_has_published_analysis(root: Path | str | None) -> bool:
    """True iff any ``analysis/<module>/published.json`` exists (skip ``runs/``).

    Stale published still counts. Health is not consulted. ``analysis/runs/`` is
    history only. Page-metrics and detection live outside ``analysis/``.
    """
    if not root:
        return False
    try:
        analysis = Path(root).expanduser() / "analysis"
    except (OSError, TypeError, ValueError):
        return False
    if not analysis.is_dir():
        return False
    try:
        children = list(analysis.iterdir())
    except OSError:
        return False
    for child in children:
        if not child.is_dir() or child.name == _RUNS_DIR_NAME:
            continue
        if (child / "published.json").is_file():
            return True
    return False


def notebook_has_detection_results(root: Path | str | None) -> bool:
    """True iff any ``detection/<detector>/published.json`` exists."""
    if not root:
        return False
    try:
        detection = Path(root).expanduser() / "detection"
    except (OSError, TypeError, ValueError):
        return False
    if not detection.is_dir():
        return False
    try:
        children = list(detection.iterdir())
    except OSError:
        return False
    for child in children:
        if child.is_dir() and (child / "published.json").is_file():
            return True
    return False


def normalize_ui_mode(raw: str | None) -> str:
    """Map aliases and known ids. Unknown (including None) → Archive.

    First visit is *not* this function: ``main()`` treats a missing session key
    as Home. Passing an unknown string still lands on Archive.
    """
    if raw in _LEGACY_MODE_ALIASES:
        return _LEGACY_MODE_ALIASES[raw]
    if raw in PAGE_SPECS_BY_ID:
        return raw
    return "Archive"


def destination_for_mode(raw: str | None) -> tuple[str, str | None]:
    """Map a mode or former View page id to ``(page_id, panel_id|None)``."""
    if raw in _VIEW_PANEL_ALIASES:
        return _VIEW_PANEL_ALIASES[raw]
    return normalize_ui_mode(raw), None


def apply_destination_to_session(
    session: MutableMapping[str, Any], raw: str | None
) -> str:
    """Write ``ui_mode`` (and a pending in-page panel when ``raw`` is an alias)."""
    mode, panel = destination_for_mode(raw)
    session["ui_mode"] = mode
    if panel:
        session[VIEW_PANEL_PENDING_KEY] = panel
    return mode


def view_panel_for(page_id: str, panel_id: str | None) -> ViewPanel | None:
    panels = VIEW_PAGE_PANELS.get(page_id)
    if not panels:
        return None
    if panel_id:
        for panel in panels:
            if panel.id == panel_id:
                return panel
    return panels[0]


def is_workflow_mode(mode: str) -> bool:
    return normalize_ui_mode(mode) in WORKFLOW_MODES


def is_view_mode(mode: str) -> bool:
    return normalize_ui_mode(mode) in VIEW_MODES


def is_open_notebook_workflow(mode: str) -> bool:
    """Workflow modes that always require an existing notebook selection.

    Import, Transcribe, and Analyse host This notebook | Batch targets; Batch does
    not need a sidebar notebook, so those pages gate selection themselves.
    """
    mode = normalize_ui_mode(mode)
    return is_workflow_mode(mode) and mode not in {
        "New notebook",
        "Import",
        "Transcribe",
        "Analyse",
    }


def nav_enabled(
    spec: PageSpec,
    *,
    has_notebook: bool,
    has_published: bool,
) -> bool:
    if spec.required_context == "none":
        return True
    if spec.required_context == "notebook":
        return has_notebook
    return has_notebook and has_published


def nav_disabled_help(spec: PageSpec, *, has_notebook: bool) -> str:
    if spec.required_context == "none":
        return ""
    if not has_notebook:
        return NAV_HELP_SELECT_NOTEBOOK
    if spec.required_context == "notebook_published":
        return NAV_HELP_ANALYSE_FIRST
    return NAV_HELP_SELECT_NOTEBOOK


def hide_context_bar(mode: str) -> bool:
    return normalize_ui_mode(mode) in CONTEXT_BAR_HIDDEN_MODES


def use_wide_layout(mode: str) -> bool:
    return normalize_ui_mode(mode) in WIDE_LAYOUT_MODES
