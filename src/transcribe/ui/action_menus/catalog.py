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
        "Open the page viewer on the first valid page of this notebook.",
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
        ActionId.EXPORT,
        "Export",
        ":material/ios_share:",
        "Open Export for this notebook.",
    ),
    ActionDef(
        ActionId.RENAME,
        "Rename",
        ":material/edit:",
        "Rename this notebook (display title only; the project folder path is unchanged).",
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
        ActionId.EXPORT,
        ActionId.RENAME,
    ),
    SectionId.VIEW_NOTEBOOK: (
        ActionId.OPEN,
        ActionId.TRANSCRIBE,
        ActionId.ANALYSE,
        ActionId.EXPORT,
        ActionId.RENAME,
        ActionId.DELETE,
    ),
}

NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
)

VIEW_NOTEBOOK_STRIP: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
    ActionId.RENAME,
    ActionId.DELETE,
)

BUILT_IN_STANDARD_MENU: tuple[ActionId, ...] = (
    ActionId.OPEN,
    ActionId.TRANSCRIBE,
    ActionId.ANALYSE,
    ActionId.EXPORT,
)


@dataclass(frozen=True)
class SectionDefaultKey:
    section: SectionId
    subject_type: str  # "notebook" | "any"


SECTION_DEFAULTS: dict[SectionDefaultKey, tuple[ActionId, ...]] = {
    SectionDefaultKey(SectionId.ARCHIVE_NOTEBOOK, "notebook"): NOTEBOOK_STRIP,
    SectionDefaultKey(SectionId.VIEW_NOTEBOOK, "notebook"): VIEW_NOTEBOOK_STRIP,
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
