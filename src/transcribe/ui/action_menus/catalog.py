"""Action catalogue: labels, icons, help, allowlists, and built-in defaults."""

from __future__ import annotations

from dataclasses import dataclass

from transcribe.ui.action_menus.ids import ActionId, SectionId
from transcribe.ui import icons as ic


@dataclass(frozen=True)
class ActionDef:
    id: ActionId
    label: str
    icon: str
    help: str


ACTIONS: tuple[ActionDef, ...] = (
    ActionDef(
        ActionId.OPEN,
        "Open",
        ic.FOLDER_OPEN,
        "Open this notebook in Reading (cover first, or first page if none).",
    ),
    ActionDef(
        ActionId.TRANSCRIBE,
        "Transcribe",
        ic.DOCUMENT_SCANNER,
        "Open the Transcribe (OCR) workflow for this notebook.",
    ),
    ActionDef(
        ActionId.ANALYSE,
        "Analyse",
        ic.ANALYTICS,
        "Open Analyse for this notebook.",
    ),
    ActionDef(
        ActionId.OVERVIEW,
        "Overview",
        ic.DASHBOARD,
        "Open Overview for this notebook (published results and page ink).",
    ),
    ActionDef(
        ActionId.REVIEW,
        "Review",
        ic.RATE_REVIEW,
        "Open Review to correct dates, empty text, and failed OCR.",
    ),
    ActionDef(
        ActionId.DETECT,
        "Detect",
        ic.SEARCH_CHECK,
        "Open Detect for poetry, lists, to-dos, quotations, beer labels, first-person I, and swear words.",
    ),
    ActionDef(
        ActionId.EXPORT,
        "Export",
        ic.SHARE,
        "Open Export for this notebook.",
    ),
    ActionDef(
        ActionId.RENAME,
        "Rename",
        ic.EDIT,
        "Rename this notebook (display title only; the notebook folder path is unchanged).",
    ),
    ActionDef(
        ActionId.DELETE,
        "Delete",
        ic.DELETE,
        "Delete this managed notebook (imported copies only). External originals are not touched.",
    ),
)

ACTIONS_BY_ID: dict[ActionId, ActionDef] = {a.id: a for a in ACTIONS}

SECTION_ALLOWLISTS: dict[SectionId, tuple[ActionId, ...]] = {
    SectionId.ARCHIVE_NOTEBOOK: (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.REVIEW,
        ActionId.ANALYSE,
        ActionId.DETECT,
        ActionId.EXPORT,
        ActionId.RENAME,
    ),
    SectionId.VIEW_NOTEBOOK: (
        ActionId.OPEN,
        ActionId.OVERVIEW,
        ActionId.TRANSCRIBE,
        ActionId.REVIEW,
        ActionId.ANALYSE,
        ActionId.DETECT,
        ActionId.EXPORT,
        ActionId.RENAME,
        ActionId.DELETE,
    ),
    SectionId.IMPORT_SUCCESS: (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.ANALYSE,
    ),
    SectionId.TRANSCRIBE_COMPLETE: (
        ActionId.OPEN,
        ActionId.REVIEW,
        ActionId.ANALYSE,
        ActionId.EXPORT,
    ),
    SectionId.ANALYSE_COMPLETE: (
        ActionId.OVERVIEW,
        ActionId.OPEN,
        ActionId.EXPORT,
        ActionId.REVIEW,
    ),
}

NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
    ActionId.REVIEW,
    ActionId.ANALYSE,
)

VIEW_NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.OVERVIEW,
    ActionId.TRANSCRIBE,
    ActionId.REVIEW,
    ActionId.ANALYSE,
    ActionId.RENAME,
    ActionId.DELETE,
)

BUILT_IN_STANDARD_MENU: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
    ActionId.ANALYSE,
    ActionId.DETECT,
    ActionId.EXPORT,
)


@dataclass(frozen=True)
class SectionDefaultKey:
    section: SectionId
    subject_type: str  # "notebook" | "any"


SECTION_DEFAULTS: dict[SectionDefaultKey, tuple[ActionId, ...]] = {
    SectionDefaultKey(SectionId.ARCHIVE_NOTEBOOK, "notebook"): NOTEBOOK_STRIP,
    SectionDefaultKey(SectionId.VIEW_NOTEBOOK, "notebook"): VIEW_NOTEBOOK_STRIP,
    SectionDefaultKey(SectionId.IMPORT_SUCCESS, "notebook"): (ActionId.TRANSCRIBE,),
    SectionDefaultKey(SectionId.TRANSCRIBE_COMPLETE, "notebook"): (ActionId.REVIEW,),
    SectionDefaultKey(SectionId.ANALYSE_COMPLETE, "notebook"): (
        ActionId.OVERVIEW,
        ActionId.OPEN,
        ActionId.EXPORT,
    ),
}


def section_default_actions(
    section: SectionId, *, subject_type: str = "notebook"
) -> tuple[ActionId, ...]:
    exact = SectionDefaultKey(section, subject_type)
    if exact in SECTION_DEFAULTS:
        return SECTION_DEFAULTS[exact]
    any_key = SectionDefaultKey(section, "any")
    if any_key in SECTION_DEFAULTS:
        return SECTION_DEFAULTS[any_key]
    return SECTION_ALLOWLISTS[section][:1]


def label_for(action: ActionId, section: SectionId | None = None) -> str:
    if action is ActionId.OVERVIEW and section is SectionId.VIEW_NOTEBOOK:
        return "View analysis"
    return ACTIONS_BY_ID[action].label


def icon_for(action: ActionId) -> str:
    return ACTIONS_BY_ID[action].icon


def help_for(action: ActionId) -> str:
    return ACTIONS_BY_ID[action].help
