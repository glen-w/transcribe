"""Validated project roots, Open page selection, and central workflow navigation."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from transcribe.domain.models import Project
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.context import (
    ActionContext,
    CanonicalIdentity,
    IdentityError,
    build_canonical_identity,
    project_root_key,
)
from transcribe.ui.action_menus.ids import NavStyle, ReturnMode, WorkflowMode
from transcribe.ui.shell import normalize_ui_mode


class ProjectRootError(ValueError):
    """Raised when a notebook root fails validation."""


def clear_page_viewer_state(session: dict | None = None) -> None:
    state = session if session is not None else st.session_state
    state["show_page_viewer"] = False
    state.pop("view_page_id", None)
    state.pop("view_page_ids", None)
    state.pop("view_entries", None)
    state.pop("view_highlight", None)
    state.pop("page_return_mode", None)


def validate_project_root(
    root: Path | str,
    *,
    projects_dir: Path | str,
) -> Path:
    """Canonicalise root; require it under projects_dir and to look like a project."""
    projects = Path(projects_dir).expanduser().resolve()
    try:
        candidate = Path(root).expanduser().resolve()
    except OSError as exc:
        raise ProjectRootError(f"unresolvable project root: {exc}") from exc

    try:
        candidate.relative_to(projects)
    except ValueError as exc:
        raise ProjectRootError(
            f"project root escapes projects directory: {candidate}"
        ) from exc

    if candidate == projects:
        raise ProjectRootError("project root must be a notebook directory, not projects root")

    if not candidate.is_dir():
        raise ProjectRootError(f"project root is not a directory: {candidate}")

    manifest = candidate / "project.json"
    if not manifest.is_file():
        raise ProjectRootError(f"missing project.json under {candidate}")

    return candidate


def viewer_page_ids(
    project: Project,
    *,
    preferred_cover_id: str | None = None,
) -> list[str]:
    """Page order for the viewer: cover first (if valid), then remaining notebook order.

    Does not mutate ``project.pages`` — analysis/OCR chronology stay as stored.
    """
    page_ids = [p.page_id for p in project.pages]
    if not page_ids:
        return []
    cover = (
        preferred_cover_id
        if preferred_cover_id is not None
        else project.cover_page_id
    )
    if cover and cover in page_ids and page_ids[0] != cover:
        return [cover] + [pid for pid in page_ids if pid != cover]
    return page_ids


def first_valid_open_page(
    project: Project,
    *,
    preferred_cover_id: str | None = None,
) -> str | None:
    """Deterministic Open target: valid cover if present, else first page in order."""
    page_ids = viewer_page_ids(project, preferred_cover_id=preferred_cover_id)
    return page_ids[0] if page_ids else None


def load_live_notebook_context(
    *,
    project_id: str,
    project_root: Path | str,
    projects_dir: Path | str,
    return_mode: ReturnMode,
    nav_style: NavStyle = NavStyle.CLICK_RERUN,
    instance_prefix: str = "nb",
) -> ActionContext:
    """Build ActionContext from live project state (not stale summary fields)."""
    try:
        root = validate_project_root(project_root, projects_dir=projects_dir)
    except ProjectRootError:
        # Soft context: strip resolves to zero capable actions; no Path in identity.
        try:
            identity = build_canonical_identity(
                project_id=project_id,
                project_root=project_root,
            )
        except IdentityError:
            identity = CanonicalIdentity(
                subject_type="notebook",
                project_id=(project_id or "").strip() or "unknown",
                project_root_key=project_root_key(Path(str(project_root))),
            )
        return ActionContext(
            identity=identity,
            return_mode=return_mode,
            nav_style=nav_style,
            instance_prefix=instance_prefix,
            projects_dir_key=project_root_key(Path(projects_dir)),
            project_exists=False,
            has_pages=False,
            page_ids=(),
            open_page_id=None,
            cover_page_id=None,
        )

    identity = build_canonical_identity(project_id=project_id, project_root=root)
    try:
        paths = open_project_paths(root)
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)
    except Exception:  # noqa: BLE001 — fail closed into empty capabilities
        return ActionContext(
            identity=identity,
            return_mode=return_mode,
            nav_style=nav_style,
            instance_prefix=instance_prefix,
            projects_dir_key=project_root_key(Path(projects_dir)),
            project_exists=False,
            has_pages=False,
            page_ids=(),
            open_page_id=None,
            cover_page_id=None,
        )

    page_ids = tuple(viewer_page_ids(project))
    open_id = first_valid_open_page(project)
    return ActionContext(
        identity=identity,
        return_mode=return_mode,
        nav_style=nav_style,
        instance_prefix=instance_prefix,
        projects_dir_key=project_root_key(Path(projects_dir)),
        project_exists=True,
        has_pages=bool(page_ids),
        page_ids=page_ids,
        open_page_id=open_id,
        cover_page_id=project.cover_page_id,
    )


def navigate_workflow(
    *,
    project_root_key: str,
    projects_dir_key: str,
    mode: WorkflowMode,
    session: dict | None = None,
    rerun: bool = True,
) -> bool:
    """Ordered transition: validate → set root → clear viewer → set mode → rerun.

    Returns False without mutating session when validation fails.
    """
    state = session if session is not None else st.session_state
    try:
        root = validate_project_root(project_root_key, projects_dir=projects_dir_key)
    except ProjectRootError:
        return False

    # Mutate only after validation succeeds.
    state["root"] = str(root)
    state["pending_notebook_root"] = str(root)
    clear_page_viewer_state(state)
    state["ui_mode"] = normalize_ui_mode(mode.value)
    if rerun and session is None:
        st.rerun()
    return True


def navigate_open(
    ctx: ActionContext,
    *,
    session: dict | None = None,
    rerun: bool = True,
) -> bool:
    """Open page viewer on the deterministic first valid page."""
    state = session if session is not None else st.session_state
    try:
        root = validate_project_root(
            ctx.identity.project_root_key,
            projects_dir=ctx.projects_dir_key,
        )
    except ProjectRootError:
        return False

    # Re-read live pages so we never trust a stale open_page_id alone.
    try:
        paths = open_project_paths(root)
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)
    except Exception:  # noqa: BLE001
        return False

    page_id = first_valid_open_page(project, preferred_cover_id=ctx.cover_page_id)
    if page_id is None:
        return False

    page_ids = viewer_page_ids(project, preferred_cover_id=ctx.cover_page_id)
    return_mode = ctx.return_mode.value

    if session is None:
        # Lazy import: page_viewer imports clear_page_viewer_state from this module.
        from transcribe.ui.page_viewer import open_page_context

        open_page_context(
            page_id=page_id,
            page_ids=page_ids,
            project_root=root,
            return_mode=return_mode,
        )
        state["ui_mode"] = return_mode
        if rerun:
            st.rerun()
        return True

    # Pure session dict path for tests (no Streamlit page_context helper).
    state["root"] = str(root)
    state["pending_notebook_root"] = str(root)
    state["view_page_id"] = page_id
    state["view_page_ids"] = page_ids
    state["view_entries"] = [
        {"page_id": pid, "project_root": str(root)} for pid in page_ids
    ]
    state["show_page_viewer"] = True
    state["page_return_mode"] = return_mode
    state["ui_mode"] = return_mode
    return True


def ensure_config_layout(runtime: RuntimePaths) -> None:
    (runtime.data_dir / "config").mkdir(parents=True, exist_ok=True)
