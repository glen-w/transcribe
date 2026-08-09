"""Typed identifiers for configurable action menus."""

from __future__ import annotations

from enum import Enum


class SectionId(str, Enum):
    ARCHIVE_NOTEBOOK = "archive_notebook"
    VIEW_NOTEBOOK = "view_notebook"


class ActionId(str, Enum):
    OPEN = "open"
    TRANSCRIBE = "transcribe"
    ANALYSE = "analyse"
    EXPORT = "export"


class ReturnMode(str, Enum):
    """Validated Open return targets (notebook listing surfaces only)."""

    ARCHIVE = "Archive"
    VIEW = "View"


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
    SectionId.VIEW_NOTEBOOK: "View — notebook row",
}


def parse_return_mode(raw: str | None) -> ReturnMode | None:
    if raw is None:
        return None
    try:
        return ReturnMode(raw)
    except ValueError:
        return None
