"""Compact tertiary icon-links for navigation actions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st

from transcribe.ui.components.info_tooltip import widget_help

ACTION_LINK_KEY_PREFIX = "tr_al_"


def action_link_key(key: str) -> str:
    if key.startswith(ACTION_LINK_KEY_PREFIX):
        return key
    return f"{ACTION_LINK_KEY_PREFIX}{key}"


def render_action_link(
    label: str,
    *,
    key: str,
    icon: str,
    on_click: Callable[..., Any] | None = None,
    args: Sequence[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    disabled: bool = False,
    help: str | None = None,
) -> bool:
    """Render one Material-icon tertiary link button. Returns click state."""
    return bool(
        st.button(
            label,
            key=action_link_key(key),
            type="tertiary",
            width="content",
            icon=icon,
            on_click=on_click,
            args=tuple(args) if args is not None else (),
            kwargs=kwargs or {},
            disabled=disabled,
            help=widget_help(help),
        )
    )
