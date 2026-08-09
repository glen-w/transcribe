"""Configurable notebook action-menu strips."""

from __future__ import annotations

from transcribe.ui.action_menus.catalog import ACTIONS, ACTIONS_BY_ID
from transcribe.ui.action_menus.ids import ActionId, ReturnMode, SectionId
from transcribe.ui.action_menus.nav import load_live_notebook_context
from transcribe.ui.action_menus.prefs import (
    INTERFACE_SCHEMA_VERSION,
    get_cached_runtime_prefs,
    load_interface_prefs,
)
from transcribe.ui.action_menus.render import render_configured_actions
from transcribe.ui.action_menus.resolve import resolve_section_actions

__all__ = [
    "ACTIONS",
    "ACTIONS_BY_ID",
    "ActionId",
    "INTERFACE_SCHEMA_VERSION",
    "ReturnMode",
    "SectionId",
    "get_cached_runtime_prefs",
    "load_interface_prefs",
    "load_live_notebook_context",
    "render_configured_actions",
    "resolve_section_actions",
]
