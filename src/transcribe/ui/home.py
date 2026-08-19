"""Home: cheap archive counts, recent notebooks, Ollama one-liner. No published.json scan."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.config.facade import get_config
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import ArchiveService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
from transcribe.ui.action_menus.ids import NavStyle, ReturnMode, SectionId
from transcribe.ui.action_menus.nav import load_live_notebook_context
from transcribe.ui.action_menus.render import render_configured_actions
from transcribe.ui.components.empty_state import EmptyCta, render_empty_state
from transcribe.ui import icons as ic
from transcribe.ui.shell import set_ui_mode

_RECENT_LIMIT = 8
_RECENT_COVER_WIDTH_PX = 112


def ollama_health_line() -> str:
    """One-line Ollama reachability for Home / Diagnostics. Never raises."""
    try:
        from transcribe.providers.ollama import OllamaVisionProvider

        base = (get_config().effective.ocr.base_url or "").strip() or "http://localhost:11434"
        provider = OllamaVisionProvider(base, request_timeout=3.0)
        provider.healthcheck()
        vision = provider.list_vision_models(refresh=False)
        n = len(vision.models)
        extra = f" · {n} vision model{'s' if n != 1 else ''}"
        if vision.error:
            extra += f" · {vision.error}"
        return f"Ollama reachable{extra}"
    except Exception as exc:  # noqa: BLE001 — Home must stay cheap
        return f"Ollama not reachable — {exc}"


def _recent_cover_thumb(project_root: Path) -> Path | None:
    """Return a cached/generated cover thumbnail for a recent notebook row."""
    try:
        paths = open_project_paths(project_root)
        project = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator()).load(
            reconcile=False
        )
        thumbs = ThumbnailService(paths)
        cover_id = thumbs.cover_page_id(project)
        if not cover_id:
            return None
        thumb = thumbs.ensure_thumb(project, cover_id)
    except Exception:  # noqa: BLE001 - Home should stay resilient
        return None
    if thumb is None or not thumb.exists():
        return None
    return thumb


def render_home(runtime: RuntimePaths, archive: ArchiveService) -> None:
    notebooks = archive.list_notebooks(order="newest")
    st.caption(ollama_health_line())

    if not notebooks:
        render_empty_state(
            kind="missing_prerequisite",
            title="No notebooks yet",
            body="Create a notebook or import pages to get started.",
            primary=EmptyCta(
                label="Create notebook",
                on_click=lambda: set_ui_mode("New notebook"),
                key="home_create",
                primary=True,
                icon=ic.CREATE,
            ),
            secondary=EmptyCta(
                label="Import",
                on_click=lambda: set_ui_mode("Import"),
                key="home_import",
                primary=False,
                icon=ic.UPLOAD,
            ),
        )
        return

    pages = sum(int(nb.page_count or 0) for nb in notebooks)
    c1, c2 = st.columns(2)
    c1.metric("Notebooks", len(notebooks))
    c2.metric("Pages", pages)

    st.markdown("#### Recent")
    for nb in notebooks[:_RECENT_LIMIT]:
        thumb = _recent_cover_thumb(nb.root)
        if thumb is not None:
            cover_col, details_col = st.columns([1, 8], gap="medium")
            with cover_col:
                st.image(str(thumb), width=_RECENT_COVER_WIDTH_PX)
            with details_col:
                st.markdown(f"**{nb.title}** · {nb.page_count} pages")
                try:
                    ctx = load_live_notebook_context(
                        project_id=nb.project_id,
                        project_root=nb.root,
                        projects_dir=runtime.projects_dir,
                        return_mode=ReturnMode.LIBRARY,
                        nav_style=NavStyle.CLICK_RERUN,
                        instance_prefix="home",
                    )
                    render_configured_actions(SectionId.VIEW_NOTEBOOK, ctx)
                except Exception:  # noqa: BLE001
                    st.caption("Actions unavailable.")
        else:
            st.markdown(f"**{nb.title}** · {nb.page_count} pages")
            try:
                ctx = load_live_notebook_context(
                    project_id=nb.project_id,
                    project_root=nb.root,
                    projects_dir=runtime.projects_dir,
                    return_mode=ReturnMode.LIBRARY,
                    nav_style=NavStyle.CLICK_RERUN,
                    instance_prefix="home",
                )
                render_configured_actions(SectionId.VIEW_NOTEBOOK, ctx)
            except Exception:  # noqa: BLE001
                st.caption("Actions unavailable.")
