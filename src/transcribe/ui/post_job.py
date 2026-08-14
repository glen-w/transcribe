"""Post-job action strips using interface-menus sections."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.models import Project
from transcribe.ui.action_menus.ids import NavStyle, ReturnMode, SectionId
from transcribe.ui.action_menus.nav import load_live_notebook_context
from transcribe.ui.action_menus.render import render_configured_actions


def render_post_job_strip(
    section: SectionId,
    *,
    project: Project,
    root: Path | str,
    projects_dir: Path | str,
    instance_prefix: str,
) -> None:
    try:
        ctx = load_live_notebook_context(
            project_id=project.id,
            project_root=root,
            projects_dir=projects_dir,
            return_mode=ReturnMode.LIBRARY,
            nav_style=NavStyle.CLICK_RERUN,
            instance_prefix=instance_prefix,
        )
    except Exception:  # noqa: BLE001
        return
    import streamlit as st

    st.markdown("#### Next")
    render_configured_actions(section, ctx)
