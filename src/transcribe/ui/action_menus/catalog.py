"""Action catalogue: labels, icons, help, allowlists, and built-in defaults."""

from __future__ import annotations

from dataclasses import dataclass

from transcribe.ui.action_menus.ids import ActionId, SectionId


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
        ":material/folder_open:",
        "Open this notebook in Reading (cover first, or first page if none).",
    ),
    ActionDef(
        ActionId.TRANSCRIBE,
        "Transcribe",
        ":material/document_scanner:",
        "Open the Transcribe (OCR) workflow for this notebook.",
    ),
    ActionDef(
        ActionId.ANALYSE,
        "Analyse",
        ":material/analytics:",
        "Open Analyse for this notebook.",
    ),
    ActionDef(
        ActionId.OVERVIEW,
        "Overview",
        ":material/dashboard:",
        "Open Overview for this notebook (published results and page ink).",
    ),
    ActionDef(
        ActionId.REVIEW,
        "Review",
        ":material/rate_review:",
        "Open Review to correct dates, empty text, and failed OCR.",
    ),
    ActionDef(
        ActionId.DETECT,
        "Detect",
        ":material/search_check:",
        "Open Detect for poetry, lists, to-dos, quotations, and beer labels.",
    ),
    ActionDef(
        ActionId.EXPORT,
        "Export",
        ":material/ios_share:",
        "Open Export for this notebook.",
    ),
    ActionDef(
        ActionId.RENAME,
        "Rename",
        ":material/edit:",
        "Rename this notebook (display title only; the notebook folder path is unchanged).",
    ),
    ActionDef(
        ActionId.DELETE,
        "Delete",
        ":material/delete:",
        "Delete this managed notebook (imported copies only). External originals are not touched.",
    ),
)

ACTIONS_BY_ID: dict[ActionId, ActionDef] = {a.id: a for a in ACTIONS}

SECTION_ALLOWLISTS: dict[SectionId, tuple[ActionId, ...]] = {
    SectionId.ARCHIVE_NOTEBOOK: (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.ANALYSE,
        ActionId.DETECT,
        ActionId.EXPORT,
        ActionId.RENAME,
    ),
    SectionId.VIEW_NOTEBOOK: (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.ANALYSE,
        ActionId.DETECT,
        ActionId.EXPORT,
        ActionId.RENAME,
        ActionId.DELETE,
    ),
    SectionId.IMPORT_SUCCESS: (
        ActionId.TRANSCRIBE,
        ActionId.OPEN,
        ActionId.ANALYSE,
    ),
    SectionId.TRANSCRIBE_COMPLETE: (
        ActionId.REVIEW,
        ActionId.OPEN,
        ActionId.ANALYSE,
        ActionId.EXPORT,
    ),
    SectionId.ANALYSE_COMPLETE: (
        ActionId.OVERVIEW,
        ActionId.EXPORT,
        ActionId.OPEN,
        ActionId.REVIEW,
    ),
}

NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
    ActionId.ANALYSE,
)

VIEW_NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
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
        ActionId.EXPORT,
        ActionId.OPEN,
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
    _ = section
    return ACTIONS_BY_ID[action].label


def icon_for(action: ActionId) -> str:
    return ACTIONS_BY_ID[action].icon


def help_for(action: ActionId) -> str:
    return ACTIONS_BY_ID[action].help
