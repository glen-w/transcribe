"""Typed identifiers for configurable action menus."""

from __future__ import annotations

from enum import Enum


class SectionId(str, Enum):
    ARCHIVE_NOTEBOOK = "archive_notebook"
    VIEW_NOTEBOOK = "view_notebook"
    IMPORT_SUCCESS = "import_success"
    TRANSCRIBE_COMPLETE = "transcribe_complete"
    ANALYSE_COMPLETE = "analyse_complete"


class ActionId(str, Enum):
    OPEN = "open"
    TRANSCRIBE = "transcribe"
    ANALYSE = "analyse"
    DETECT = "detect"
    EXPORT = "export"
    RENAME = "rename"
    DELETE = "delete"
    OVERVIEW = "overview"
    REVIEW = "review"


class ReturnMode(str, Enum):
    """Open / jump return targets.

    ``VIEW`` is a legacy listing alias (normalises to Library). Open always
    lands on Reading; ``page_return_mode`` stores the listing/source page.
    """

    ARCHIVE = "Archive"
    LIBRARY = "Library"
    VIEW = "View"
    READING = "Reading"
    SEARCH = "Search"
    DETECT = "Detect"


class NavStyle(str, Enum):
    """How action links commit navigation.

    ``ON_CLICK``: Streamlit ``on_click`` callback that mutates session state.
    Safe only outside ``@st.fragment``.

    ``CLICK_RERUN``: Activate on click return value, then explicit ``st.rerun()``.
    """

    ON_CLICK = "on_click"
    CLICK_RERUN = "click_rerun"


class StandardMenuMode(str, Enum):
    BUILT_IN = "built_in"
    CUSTOM = "custom"


class SectionMenuMode(str, Enum):
    USE_STANDARD = "use_standard"
    SECTION_DEFAULT = "section_default"
    MANUAL = "manual"


class WorkflowMode(str, Enum):
    TRANSCRIBE = "Transcribe"
    ANALYSE = "Analyse"
    EXPORT = "Export"


SECTION_ORDER: tuple[SectionId, ...] = tuple(SectionId)
ACTION_ORDER: tuple[ActionId, ...] = tuple(ActionId)

SECTION_LABELS: dict[SectionId, str] = {
    SectionId.ARCHIVE_NOTEBOOK: "Archive — notebook card",
    SectionId.VIEW_NOTEBOOK: "Library — notebook row",
    SectionId.IMPORT_SUCCESS: "Import — after success",
    SectionId.TRANSCRIBE_COMPLETE: "Transcribe — after complete",
    SectionId.ANALYSE_COMPLETE: "Analyse — after this-notebook complete",
}

_RETURN_ALIASES: dict[str, ReturnMode] = {
    "View": ReturnMode.VIEW,
    "Library": ReturnMode.LIBRARY,
}


def parse_return_mode(raw: str | None) -> ReturnMode | None:
    if raw is None:
        return None
    alias = _RETURN_ALIASES.get(raw)
    if alias is not None:
        return alias
    try:
        return ReturnMode(raw)
    except ValueError:
        return None


def listing_return_mode(mode: ReturnMode) -> str:
    """Session ``page_return_mode`` for Back after Open (Library, not View)."""
    if mode in {ReturnMode.VIEW, ReturnMode.LIBRARY}:
        return ReturnMode.LIBRARY.value
    return mode.value
