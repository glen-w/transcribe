"""Closed action handler registry: availability + render."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from transcribe.ui.action_menus.catalog import ACTIONS, help_for, icon_for, label_for
from transcribe.ui.action_menus.context import ActionContext, ContextCapabilities
from transcribe.ui.action_menus.ids import ActionId, NavStyle, SectionId, WorkflowMode
from transcribe.ui.action_menus.nav import navigate_open, navigate_workflow
from transcribe.ui.components.action_links import render_action_link


@dataclass(frozen=True)
class ActionHandler:
    is_available: Callable[[ActionContext, ContextCapabilities], bool]
    render: Callable[..., None]


def _available_open(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
    return caps.project_exists and caps.has_pages


def _available_workflow(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
    return caps.project_exists


def _button(
    ctx: ActionContext,
    *,
    action: ActionId,
    section: SectionId,
    key: str,
    on_activate: Callable[[], None],
) -> None:
    label = label_for(action, section)
    icon = icon_for(action)
    help_text = help_for(action)
    if ctx.nav_style == NavStyle.ON_CLICK:
        render_action_link(
            label, key=key, icon=icon, help=help_text, on_click=on_activate
        )
    else:
        if render_action_link(label, key=key, icon=icon, help=help_text):
            on_activate()
            st.rerun()


def _render_open(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    def _go() -> None:
        navigate_open(ctx, rerun=False)

    _button(ctx, action=ActionId.OPEN, section=section, key=key, on_activate=_go)


def _render_transcribe(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    def _go() -> None:
        navigate_workflow(
            project_root_key=ctx.identity.project_root_key,
            projects_dir_key=ctx.projects_dir_key,
            mode=WorkflowMode.TRANSCRIBE,
            rerun=False,
        )

    _button(
        ctx, action=ActionId.TRANSCRIBE, section=section, key=key, on_activate=_go
    )


def _render_analyse(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    def _go() -> None:
        navigate_workflow(
            project_root_key=ctx.identity.project_root_key,
            projects_dir_key=ctx.projects_dir_key,
            mode=WorkflowMode.ANALYSE,
            rerun=False,
        )

    _button(ctx, action=ActionId.ANALYSE, section=section, key=key, on_activate=_go)


def _render_export(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    def _go() -> None:
        navigate_workflow(
            project_root_key=ctx.identity.project_root_key,
            projects_dir_key=ctx.projects_dir_key,
            mode=WorkflowMode.EXPORT,
            rerun=False,
        )

    _button(ctx, action=ActionId.EXPORT, section=section, key=key, on_activate=_go)


HANDLERS: dict[ActionId, ActionHandler] = {
    ActionId.OPEN: ActionHandler(_available_open, _render_open),
    ActionId.TRANSCRIBE: ActionHandler(_available_workflow, _render_transcribe),
    ActionId.ANALYSE: ActionHandler(_available_workflow, _render_analyse),
    ActionId.EXPORT: ActionHandler(_available_workflow, _render_export),
}


def assert_handler_registry_closed() -> None:
    """Every catalogue action has exactly one handler; no undeclared handlers."""
    catalogue_ids = {a.id for a in ACTIONS}
    handler_ids = set(HANDLERS)
    if catalogue_ids != handler_ids:
        missing = catalogue_ids - handler_ids
        extra = handler_ids - catalogue_ids
        raise AssertionError(
            f"handler registry not closed: missing={missing!r} extra={extra!r}"
        )


assert_handler_registry_closed()


def is_action_available(
    action: ActionId, ctx: ActionContext, caps: ContextCapabilities
) -> bool:
    handler = HANDLERS.get(action)
    if handler is None:
        return False
    return handler.is_available(ctx, caps)


def render_action(
    action: ActionId, ctx: ActionContext, *, section: SectionId, key: str
) -> None:
    HANDLERS[action].render(ctx, section=section, key=key)
