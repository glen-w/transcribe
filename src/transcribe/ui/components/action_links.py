"""Compact tertiary icon-links for navigation actions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st

from transcribe.ui.action_menus.ids import ActionDisplay
from transcribe.ui.components.info_tooltip import widget_help

ACTION_LINK_KEY_PREFIX = "tr_al_"
_ICON_ONLY_LABEL = "\u00a0"


def action_link_key(key: str) -> str:
    if key.startswith(ACTION_LINK_KEY_PREFIX):
        return key
    return f"{ACTION_LINK_KEY_PREFIX}{key}"


def action_link_chrome(
    label: str,
    icon: str,
    display: ActionDisplay,
) -> tuple[str, str | None]:
    """Map display mode to Streamlit button label and optional Material icon."""
    if display is ActionDisplay.ICON:
        return (_ICON_ONLY_LABEL, icon)
    if display is ActionDisplay.TEXT:
        return (label, None)
    return (label, icon)


def action_link_help(
    label: str,
    help_text: str | None,
    display: ActionDisplay,
) -> str | None:
    """Resolve tooltip: icon-only always shows the action name; else instructional help."""
    if display is ActionDisplay.ICON:
        return label
    return widget_help(help_text)


def render_action_link(
    label: str,
    *,
    key: str,
    icon: str | None = None,
    on_click: Callable[..., Any] | None = None,
    args: Sequence[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    disabled: bool = False,
    help: str | None = None,
    display: ActionDisplay = ActionDisplay.BOTH,
) -> bool:
    """Render one Material-icon tertiary link button. Returns click state."""
    btn_label, btn_icon = action_link_chrome(label, icon or "", display)
    btn_help = action_link_help(label, help, display)
    button_kwargs: dict[str, Any] = {
        "key": action_link_key(key),
        "type": "tertiary",
        "width": "content",
        "on_click": on_click,
        "args": tuple(args) if args is not None else (),
        "kwargs": kwargs or {},
        "disabled": disabled,
        "help": btn_help,
    }
    if btn_icon is not None:
        button_kwargs["icon"] = btn_icon
    return bool(st.button(btn_label, **button_kwargs))
