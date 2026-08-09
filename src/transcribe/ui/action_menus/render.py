"""Render configured action strips with per-notebook failure isolation."""

from __future__ import annotations

import hashlib
import logging

import streamlit as st

from transcribe.ui.action_menus.context import ActionContext
from transcribe.ui.action_menus.handlers import render_action
from transcribe.ui.action_menus.ids import ActionId, SectionId
from transcribe.ui.action_menus.prefs import InterfaceMenuPrefs
from transcribe.ui.action_menus.resolve import resolve_section_actions

logger = logging.getLogger(__name__)


def action_widget_key(
    *,
    instance_prefix: str,
    section: SectionId,
    project_id: str,
    action: ActionId,
) -> str:
    """Namespace by section + stable notebook id + action (plus short digest)."""
    digest = hashlib.sha1(
        f"{instance_prefix}|{section.value}|{project_id}|{action.value}".encode()
    ).hexdigest()[:10]
    return f"{instance_prefix}__{section.value}__{project_id}__{action.value}__{digest}"


def render_configured_actions(
    section: SectionId,
    ctx: ActionContext,
    *,
    prefs: InterfaceMenuPrefs | None = None,
) -> list[ActionId]:
    """Resolve and render the action strip. Failures are isolated to this call.

    Returns resolved IDs (may be empty). Never raises into the caller for
    ordinary resolve/render faults.
    """
    try:
        actions = resolve_section_actions(section, ctx, prefs=prefs)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "action menu resolve failed for %s/%s: %s",
            section.value,
            ctx.identity.project_id,
            exc,
        )
        st.caption("Actions unavailable.")
        return []

    if not actions:
        return []

    try:
        cols = st.columns(len(actions), gap="small")
        for col, action in zip(cols, actions):
            key = action_widget_key(
                instance_prefix=ctx.instance_prefix,
                section=section,
                project_id=ctx.identity.project_id,
                action=action,
            )
            with col:
                try:
                    render_action(action, ctx, section=section, key=key)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "action render failed %s for %s: %s",
                        action.value,
                        ctx.identity.project_id,
                        exc,
                    )
                    st.caption(f"{action.value} unavailable")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "action strip failed for %s/%s: %s",
            section.value,
            ctx.identity.project_id,
            exc,
        )
        st.caption("Actions unavailable.")
        return []

    return actions
