"""Resolve configured action IDs for a section + context."""

from __future__ import annotations

from transcribe.ui.action_menus.catalog import (
    BUILT_IN_STANDARD_MENU,
    SECTION_ALLOWLISTS,
    section_default_actions,
)
from transcribe.ui.action_menus.context import (
    ActionContext,
    capabilities_from_context,
)
from transcribe.ui.action_menus.ids import ActionId, SectionId
from transcribe.ui.action_menus.prefs import (
    InterfaceMenuPrefs,
    get_cached_runtime_prefs,
)


def _standard_menu_ids(prefs: InterfaceMenuPrefs) -> list[ActionId]:
    if prefs.standard_menu_mode == "built_in":
        return list(BUILT_IN_STANDARD_MENU)
    return list(prefs.standard_menu)


def configured_actions_for_section(
    prefs: InterfaceMenuPrefs,
    section: SectionId,
    *,
    subject_type: str = "notebook",
    apply_capabilities: bool = False,
    ctx: ActionContext | None = None,
) -> list[ActionId]:
    """Return configured action IDs, optionally capability-filtered.

    Order: configured candidate order, intersected with section allowlist
    (allowlist membership only — candidate order preserved).
    """
    section_prefs = prefs.sections.get(section)
    if section_prefs is None or not section_prefs.show_menu:
        return []

    if section_prefs.mode == "manual":
        candidates = list(section_prefs.selected)
    elif section_prefs.mode == "use_standard":
        candidates = _standard_menu_ids(prefs)
    else:
        candidates = list(
            section_default_actions(section, subject_type=subject_type)
        )

    allow = set(SECTION_ALLOWLISTS[section])
    seen: set[ActionId] = set()
    deduped: list[ActionId] = []
    for a in candidates:
        if a in allow and a not in seen:
            seen.add(a)
            deduped.append(a)

    if not apply_capabilities:
        return deduped
    if ctx is None:
        return deduped

    from transcribe.ui.action_menus.handlers import is_action_available

    caps = capabilities_from_context(ctx)
    return [a for a in deduped if is_action_available(a, ctx, caps)]


def resolve_section_actions(
    section: SectionId,
    ctx: ActionContext,
    *,
    prefs: InterfaceMenuPrefs | None = None,
) -> list[ActionId]:
    """Full runtime resolve for a strip (pure given prefs + ctx)."""
    prefs = prefs or get_cached_runtime_prefs()
    return configured_actions_for_section(
        prefs,
        section,
        subject_type=ctx.identity.subject_type,
        apply_capabilities=True,
        ctx=ctx,
    )
