"""Closed action handler registry: availability + render."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from transcribe.errors import JobConflictError, ProjectError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import bump_archive_generation
from transcribe.services.project import (
    ProjectService,
    delete_managed_notebook,
    open_project_paths,
)
from transcribe.ui.action_menus.catalog import ACTIONS, help_for, icon_for, label_for
from transcribe.ui.action_menus.context import ActionContext, ContextCapabilities
from transcribe.ui.action_menus.ids import ActionId, NavStyle, SectionId, WorkflowMode
from transcribe.ui.action_menus.nav import (
    ProjectRootError,
    clear_page_viewer_state,
    navigate_open,
    navigate_workflow,
    validate_project_root,
)
from transcribe.ui.components.action_links import render_action_link


@dataclass(frozen=True)
class ActionHandler:
    is_available: Callable[[ActionContext, ContextCapabilities], bool]
    render: Callable[..., None]


def _available_open(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
    return caps.project_exists and caps.has_pages


def _available_workflow(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
    return caps.project_exists


def _available_delete(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
    return caps.project_exists


def _available_rename(_ctx: ActionContext, caps: ContextCapabilities) -> bool:
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


def _delete_pending_key(project_id: str) -> str:
    return f"am_delete_pending__{project_id}"


def _rename_pending_key(project_id: str) -> str:
    return f"am_rename_pending__{project_id}"


def _notebook_title_for_dialog(
    *,
    project_root_key: str,
    projects_dir_key: str,
    fallback: str,
) -> str:
    try:
        root = validate_project_root(project_root_key, projects_dir=projects_dir_key)
        paths = open_project_paths(root)
        project = ProjectService(
            paths, clock=SystemClock(), ids=UuidGenerator()
        ).load(reconcile=False)
        title = (project.title or "").strip()
        return title or fallback
    except Exception:  # noqa: BLE001
        return fallback


def _scrub_viewer_entries_for_deleted(root: Path) -> None:
    """Remove deleted notebook from Prev/Next nav even if another project is open."""
    entries = st.session_state.get("view_entries")
    if not entries:
        return
    try:
        deleted = str(root.resolve())
    except OSError:
        deleted = str(root)
    kept: list[dict] = []
    for entry in entries:
        raw = entry.get("project_root") if isinstance(entry, dict) else None
        if not raw:
            continue
        try:
            if str(Path(str(raw)).expanduser().resolve()) == deleted:
                continue
        except OSError:
            continue
        kept.append(entry)
    if not kept:
        clear_page_viewer_state()
        return
    st.session_state["view_entries"] = kept
    st.session_state["view_page_ids"] = [
        str(e.get("page_id")) for e in kept if e.get("page_id")
    ]
    current_id = st.session_state.get("view_page_id")
    if current_id and current_id not in st.session_state["view_page_ids"]:
        st.session_state["view_page_id"] = st.session_state["view_page_ids"][0]


def _clear_session_if_deleted(root: Path) -> None:
    _scrub_viewer_entries_for_deleted(root)
    current = st.session_state.get("root")
    if not current:
        return
    try:
        if Path(current).expanduser().resolve() != root:
            return
    except OSError:
        return
    st.session_state.pop("root", None)
    st.session_state["pending_notebook_root"] = ""
    clear_page_viewer_state()


@st.dialog("Delete notebook")
def _delete_notebook_dialog(
    *,
    project_id: str,
    project_root_key: str,
    projects_dir_key: str,
    title: str,
) -> None:
    st.markdown(f"Delete **{title}** from Transcribe?")
    st.caption(
        "Removes this notebook's managed directory (imported files, OCR results, "
        "and analysis). External originals outside Transcribe are not deleted."
    )
    err = st.session_state.pop(f"am_delete_error__{project_id}", None)
    if err:
        st.error(err)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", key=f"am_del_cancel__{project_id}", width="stretch"):
            st.rerun()
    with c2:
        if st.button(
            "Delete permanently",
            key=f"am_del_ok__{project_id}",
            type="primary",
            width="stretch",
        ):
            try:
                deleted = delete_managed_notebook(
                    project_root_key,
                    projects_dir=projects_dir_key,
                )
            except (ProjectError, JobConflictError, TranscribeError, OSError) as exc:
                st.session_state[f"am_delete_error__{project_id}"] = str(exc)
                st.session_state[_delete_pending_key(project_id)] = True
                st.rerun()
                return
            _clear_session_if_deleted(deleted)
            try:
                bump_archive_generation(build_runtime_paths())
            except Exception:  # noqa: BLE001 — listing refresh is best-effort
                pass
            st.toast(f"Deleted notebook “{title}”")
            st.rerun()


def _open_delete_dialog(ctx: ActionContext) -> None:
    title = _notebook_title_for_dialog(
        project_root_key=ctx.identity.project_root_key,
        projects_dir_key=ctx.projects_dir_key,
        fallback=ctx.identity.project_id,
    )
    _delete_notebook_dialog(
        project_id=ctx.identity.project_id,
        project_root_key=ctx.identity.project_root_key,
        projects_dir_key=ctx.projects_dir_key,
        title=title,
    )


def _render_delete(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    pending = _delete_pending_key(ctx.identity.project_id)
    if st.session_state.pop(pending, False):
        _open_delete_dialog(ctx)

    label = label_for(ActionId.DELETE, section)
    icon = icon_for(ActionId.DELETE)
    help_text = help_for(ActionId.DELETE)

    if ctx.nav_style == NavStyle.ON_CLICK:

        def _arm() -> None:
            st.session_state[pending] = True

        render_action_link(label, key=key, icon=icon, help=help_text, on_click=_arm)
    else:
        if render_action_link(label, key=key, icon=icon, help=help_text):
            _open_delete_dialog(ctx)


@st.dialog("Rename notebook")
def _rename_notebook_dialog(
    *,
    project_id: str,
    project_root_key: str,
    projects_dir_key: str,
    title: str,
) -> None:
    st.caption("Changes the display title only. The notebook folder path is unchanged.")
    err = st.session_state.pop(f"am_rename_error__{project_id}", None)
    if err:
        st.error(err)

    new_title = st.text_input(
        "Notebook name",
        value=title,
        key=f"am_rename_input__{project_id}",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", key=f"am_rename_cancel__{project_id}", width="stretch"):
            st.rerun()
    with c2:
        if st.button(
            "Save name",
            key=f"am_rename_ok__{project_id}",
            type="primary",
            width="stretch",
        ):
            cleaned = (new_title or "").strip()
            if not cleaned:
                st.session_state[f"am_rename_error__{project_id}"] = (
                    "Notebook name cannot be empty."
                )
                st.session_state[_rename_pending_key(project_id)] = True
                st.rerun()
                return
            try:
                root = validate_project_root(
                    project_root_key, projects_dir=projects_dir_key
                )
                paths = open_project_paths(root)
                ProjectService(
                    paths, clock=SystemClock(), ids=UuidGenerator()
                ).update_notebook_metadata(title=cleaned)
            except (ProjectError, ProjectRootError, TranscribeError, OSError) as exc:
                st.session_state[f"am_rename_error__{project_id}"] = str(exc)
                st.session_state[_rename_pending_key(project_id)] = True
                st.rerun()
                return
            try:
                bump_archive_generation(build_runtime_paths())
            except Exception:  # noqa: BLE001 — listing refresh is best-effort
                pass
            st.toast(f"Renamed notebook to “{cleaned}”")
            st.rerun()


def _open_rename_dialog(ctx: ActionContext) -> None:
    title = _notebook_title_for_dialog(
        project_root_key=ctx.identity.project_root_key,
        projects_dir_key=ctx.projects_dir_key,
        fallback=ctx.identity.project_id,
    )
    _rename_notebook_dialog(
        project_id=ctx.identity.project_id,
        project_root_key=ctx.identity.project_root_key,
        projects_dir_key=ctx.projects_dir_key,
        title=title,
    )


def _render_rename(ctx: ActionContext, *, section: SectionId, key: str) -> None:
    pending = _rename_pending_key(ctx.identity.project_id)
    if st.session_state.pop(pending, False):
        _open_rename_dialog(ctx)

    label = label_for(ActionId.RENAME, section)
    icon = icon_for(ActionId.RENAME)
    help_text = help_for(ActionId.RENAME)

    if ctx.nav_style == NavStyle.ON_CLICK:

        def _arm() -> None:
            st.session_state[pending] = True

        render_action_link(label, key=key, icon=icon, help=help_text, on_click=_arm)
    else:
        if render_action_link(label, key=key, icon=icon, help=help_text):
            _open_rename_dialog(ctx)


HANDLERS: dict[ActionId, ActionHandler] = {
    ActionId.OPEN: ActionHandler(_available_open, _render_open),
    ActionId.TRANSCRIBE: ActionHandler(_available_workflow, _render_transcribe),
    ActionId.ANALYSE: ActionHandler(_available_workflow, _render_analyse),
    ActionId.EXPORT: ActionHandler(_available_workflow, _render_export),
    ActionId.RENAME: ActionHandler(_available_rename, _render_rename),
    ActionId.DELETE: ActionHandler(_available_delete, _render_delete),
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
