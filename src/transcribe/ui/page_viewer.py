"""Canonical page viewer shared by Archive, Search, and Workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.domain.dates import (
    DATE_SOURCE_EXTRACTED,
    DATE_SOURCE_INHERITED,
    format_approve_all_dates_help,
    looks_like_unparsed_date_stamp,
    parse_date_input,
)
from transcribe.domain.models import CleanupRecord, OCRAttempt, Project
from transcribe.errors import JobConflictError, ProjectError, TranscribeError
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.paths import ProjectPaths
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import bump_archive_generation, highlight_terms
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
from transcribe.ui import icons as ic
from transcribe.ui.action_menus.nav import clear_page_viewer_state, notebook_view_entries
from transcribe.ui.components.info_tooltip import render_caption_with_info

# User-facing implications for each cleanup mode (matches cleanup prompts + validator).
_CLEANUP_MODE_HELP: dict[str, str] = {
    "strip_leak": (
        "Strip leakage only: removes leaked system/instruction text and prompt "
        "artefacts that are not part of the page. Does not paraphrase, rewrite, "
        "or invent content. Tightest validator budgets — large edits are rejected "
        "and raw OCR is kept."
    ),
    "sanitize_light": (
        "Light sanitize: strips leakage and fixes only obvious OCR artefacts "
        "(broken whitespace, duplicated punctuation) while staying faithful to "
        "the page. Does not paraphrase meaning or add new content. Validator "
        "allows modest length change; rejected output keeps raw OCR."
    ),
    "rewrite": (
        "Broader rewrite: may lightly polish spelling/punctuation and remove "
        "leaked instruction text while preserving the author's meaning. More "
        "latitude than sanitize_light, but still must stay grounded in the OCR "
        "source. Rejected output keeps raw OCR."
    ),
}


def _transcription_model_label(attempt: OCRAttempt | None) -> str | None:
    """Vision OCR model recorded on the active attempt, if any."""
    if attempt is None:
        return None
    if attempt.provenance and attempt.provenance.model_name:
        return attempt.provenance.model_name
    raw = attempt.fingerprint_payload.get("model_name")
    if raw:
        return str(raw)
    return None


def _transcription_model_help(attempt: OCRAttempt | None, model_label: str) -> str:
    """Tooltip detailing the vision OCR model used for this attempt."""
    parts = [
        f"Vision OCR model for this page: {model_label}.",
        "Reads the page image and produces the transcription (before any cleanup).",
    ]
    prov = attempt.provenance if attempt else None
    if prov is None:
        return " ".join(parts)
    if prov.model_identity_verified:
        digest = (prov.model_digest or "").strip()
        if digest:
            short = digest if len(digest) <= 16 else f"{digest[:12]}…"
            parts.append(f"Identity verified ({short}).")
        else:
            parts.append("Identity verified.")
        parts.append("Matching fingerprints can skip re-OCR.")
    else:
        parts.append("Identity unverified — fingerprint skip is disabled for this model tag.")
    parts.append(f"Prompt: {prov.prompt_id} v{prov.prompt_version}.")
    profile = prov.preprocess_profile or "none"
    parts.append(f"Preprocess: {profile}.")
    return " ".join(parts)


def _cleanup_mode_help(cleanup: CleanupRecord) -> str:
    """Tooltip detailing implications of the cleanup mode (and model if known)."""
    mode = (cleanup.mode or "").strip()
    base = _CLEANUP_MODE_HELP.get(
        mode,
        (
            f"Cleanup mode “{mode or 'unknown'}”: second-pass text model after "
            "vision OCR. Failures and validator rejections keep raw OCR."
        ),
    )
    model = (cleanup.model_name or "").strip()
    if model:
        return f"{base} Cleanup model: {model}."
    return base


def _escape_markdown_plain(text: str) -> str:
    """Escape markdown so st.caption/st.markdown never promote OCR into headings."""
    return escape_markdown_plain(text)


def _render_transcription_plain(text: str) -> None:
    """Show OCR / user transcription without interpreting markdown syntax."""
    st.markdown(_escape_markdown_plain(text))


def _ocr_compare_preview(raw_text: str | None, *, limit: int = 120) -> str:
    """One-line plain preview for Compare OCR attempts (safe for st.caption)."""
    preview = " ".join((raw_text or "").split())
    if not preview:
        return "(empty)"
    if len(preview) > limit:
        preview = preview[: limit - 3] + "…"
    return _escape_markdown_plain(preview)


def _shows_compare_attempts(result: Any) -> bool:
    """True when Compare OCR attempts UI will render for this page result."""
    if result is None:
        return False
    succeeded = [
        a for a in result.attempts if a.status == "succeeded" and (a.raw_text or "").strip()
    ]
    if len(succeeded) >= 2:
        return True
    return any((a.attempt_kind or "vision") == "composite" for a in succeeded)


def _reader_cover_page_id(project: Project) -> str | None:
    """Cover page used by Reader semantics, falling back to the first page."""
    return project.cover_page_id or (project.pages[0].page_id if project.pages else None)


# Cap page-scan width in multi-model compare so Prefer/Promote stays primary.
_COMPARE_SCAN_IMAGE_WIDTH_PX = 320


def _render_attempt_compare(
    *,
    projects: ProjectService,
    project: Project,
    page_id: str,
    result: Any,
) -> None:
    """Compare / Prefer UI for multipass or multi-attempt pages."""
    from transcribe.domain.models import DEFAULT_PREFER_MODE, PREFER_MODES

    if not _shows_compare_attempts(result):
        return
    succeeded = [
        a for a in result.attempts if a.status == "succeeded" and (a.raw_text or "").strip()
    ]

    with st.expander("Compare OCR attempts", expanded=True):
        settings = project.settings
        prefer_mode = (
            settings.prefer_mode if settings.prefer_mode in PREFER_MODES else DEFAULT_PREFER_MODE
        )
        mode_labels = {
            "prefer_is_promote": "Prefer = promote (default)",
            "prefer_only": "Prefer only (stats / fine-tune)",
            "prefer_promote_with_edit_gate": "Prefer + promote with edit gate",
        }
        new_mode = st.selectbox(
            "Prefer mode (this notebook)",
            options=list(mode_labels.keys()),
            format_func=lambda m: mode_labels[m],
            index=list(mode_labels.keys()).index(prefer_mode),
            key=f"prefer_mode_{page_id}",
        )
        auto_comp = st.checkbox(
            "Auto-activate composite after multipass",
            value=bool(settings.auto_activate_composite),
            key=f"auto_comp_{page_id}",
        )
        if new_mode != prefer_mode or auto_comp != settings.auto_activate_composite:
            if st.button("Save compare settings", key=f"save_cmp_{page_id}", icon=ic.SAVE):
                settings.prefer_mode = new_mode
                settings.auto_activate_composite = bool(auto_comp)
                projects.save_settings(project, settings)
                st.rerun()

        vision = [a for a in succeeded if (a.attempt_kind or "vision") == "vision"]
        composites = [a for a in succeeded if (a.attempt_kind or "vision") == "composite"]

        # Order vision by comparison rank when present
        ordered_vision = list(vision)
        if result.comparison and result.comparison.ranked_attempt_ids:
            rank_map = {aid: i for i, aid in enumerate(result.comparison.ranked_attempt_ids)}
            ordered_vision.sort(key=lambda a: rank_map.get(a.attempt_id, 10_000))
        else:
            ordered_vision.sort(key=lambda a: a.started_at, reverse=True)

        st.caption("Ranked vision outputs" if result.comparison else "Vision outputs")
        for attempt in ordered_vision:
            _render_attempt_card(
                projects=projects,
                page_id=page_id,
                result=result,
                attempt=attempt,
                prefer_mode=new_mode,
                band="vision",
            )

        if composites:
            st.markdown("---")
            st.caption("Composite (merged — not ranked with raws)")
            for attempt in composites:
                _render_attempt_card(
                    projects=projects,
                    page_id=page_id,
                    result=result,
                    attempt=attempt,
                    prefer_mode=new_mode,
                    band="composite",
                )

        if len(ordered_vision) + len(composites) >= 2:
            ids = [a.attempt_id for a in ordered_vision + composites]
            labels = {
                a.attempt_id: (
                    f"{(a.provenance.model_name if a.provenance else a.attempt_kind)}"
                    f" · {a.attempt_id[:8]}"
                )
                for a in ordered_vision + composites
            }
            c1, c2 = st.columns(2)
            left_id = c1.selectbox(
                "Diff A",
                ids,
                format_func=lambda i: labels.get(i, i),
                key=f"diff_a_{page_id}",
            )
            right_id = c2.selectbox(
                "Diff B",
                ids,
                index=min(1, len(ids) - 1),
                format_func=lambda i: labels.get(i, i),
                key=f"diff_b_{page_id}",
            )
            left_a = result.attempt_by_id(left_id)
            right_a = result.attempt_by_id(right_id)
            d1, d2 = st.columns(2)
            d1.text_area(
                "A",
                value=(left_a.raw_text if left_a else "") or "",
                height=160,
                key=f"diff_ta_{page_id}",
            )
            d2.text_area(
                "B",
                value=(right_a.raw_text if right_a else "") or "",
                height=160,
                key=f"diff_tb_{page_id}",
            )


def _render_attempt_card(
    *,
    projects: ProjectService,
    page_id: str,
    result: Any,
    attempt: OCRAttempt,
    prefer_mode: str,
    band: str,
) -> None:
    model = (
        attempt.provenance.model_name
        if attempt.provenance and attempt.provenance.model_name
        else attempt.attempt_kind
    )
    chips = []
    if result.active_attempt_id == attempt.attempt_id:
        chips.append("active")
    if result.preferred_attempt_id == attempt.attempt_id:
        chips.append("preferred")
    chip_txt = f" [{' · '.join(chips)}]" if chips else ""
    st.markdown(f"**{model}**{chip_txt}")
    # OCR often starts with `#` / `-` / `*` (faithful_markdown); st.caption
    # would otherwise render those as huge headings or list items.
    st.caption(_ocr_compare_preview(attempt.raw_text))
    b1, b2, b3 = st.columns(3)
    if b1.button("Prefer", key=f"pref_{band}_{attempt.attempt_id}", icon=ic.PREFER):
        try:
            edit_choice = None
            if prefer_mode == "prefer_promote_with_edit_gate" and result.edited_text is not None:
                edit_choice = st.session_state.get(f"edit_gate_{page_id}", "keep_edit")
            projects.set_preferred_attempt(
                page_id,
                attempt.attempt_id,
                mode=prefer_mode,
                edit_gate_choice=edit_choice,
            )
            bump_archive_generation(build_runtime_paths())
            st.rerun()
        except TranscribeError as exc:
            if "edit_gate_choice" in str(exc):
                st.warning("Choose keep edit or adopt new below, then Prefer again.")
                st.session_state[f"need_edit_gate_{page_id}"] = attempt.attempt_id
            else:
                st.error(str(exc))
    if b2.button("Promote", key=f"prom_{band}_{attempt.attempt_id}", icon=ic.PROMOTE):
        try:
            projects.set_active_attempt(page_id, attempt.attempt_id)
            bump_archive_generation(build_runtime_paths())
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))
    with b3.expander("Text", expanded=False):
        st.text(attempt.raw_text or "")

    if st.session_state.get(f"need_edit_gate_{page_id}") == attempt.attempt_id:
        choice = st.radio(
            "Human edit is present — how to prefer?",
            options=["keep_edit", "adopt_new"],
            format_func=lambda x: (
                "Keep edit overlay" if x == "keep_edit" else "Adopt new (clear edit)"
            ),
            key=f"edit_gate_{page_id}",
        )
        if st.button("Confirm Prefer", key=f"confirm_pref_{attempt.attempt_id}", icon=ic.CHECK):
            try:
                projects.set_preferred_attempt(
                    page_id,
                    attempt.attempt_id,
                    mode="prefer_promote_with_edit_gate",
                    edit_gate_choice=choice,
                )
                st.session_state.pop(f"need_edit_gate_{page_id}", None)
                bump_archive_generation(build_runtime_paths())
                st.rerun()
            except TranscribeError as exc:
                st.error(str(exc))


_NAV_SCOPE_SEARCH = "search"
_NAV_SCOPE_NOTEBOOK = "notebook"
_NAV_SCOPE_LABELS = ("Search results", "This notebook")
_NAV_SCOPE_BY_LABEL = {
    "Search results": _NAV_SCOPE_SEARCH,
    "This notebook": _NAV_SCOPE_NOTEBOOK,
}
_NAV_LABEL_BY_SCOPE = {value: label for label, value in _NAV_SCOPE_BY_LABEL.items()}


def _is_search_reading_context(*, read_only: bool) -> bool:
    return read_only and st.session_state.get("page_return_mode") == "Search"


def _snap_page_to_search_scope(
    page_id: str | None,
    search_entries: list[dict[str, str]],
    notebook_root: str | Path | None,
) -> str | None:
    """Keep current page if it is a hit; else first hit in notebook; else first overall."""
    if not search_entries:
        return page_id
    if page_id and any(entry["page_id"] == page_id for entry in search_entries):
        return page_id
    if notebook_root:
        try:
            root_key = str(Path(notebook_root).expanduser().resolve())
        except OSError:
            root_key = str(notebook_root)
        for entry in search_entries:
            try:
                same_root = str(Path(entry["project_root"]).expanduser().resolve()) == root_key
            except OSError:
                same_root = str(entry["project_root"]) == str(notebook_root)
            if same_root:
                return entry["page_id"]
    return search_entries[0]["page_id"]


def _search_hit_entries(
    *,
    view_entries: list[dict[str, Any]] | None,
    page_ids: list[str] | None,
    project_root: str | Path | None,
) -> list[dict[str, str]]:
    """Preserve or rebuild the Search Prev/Next hit list."""
    existing_base = st.session_state.get("view_entries_base")
    if isinstance(existing_base, list) and existing_base:
        return _normalize_entries(
            page_ids=page_ids,
            project_root=project_root,
            view_entries=existing_base,
        )
    if view_entries is not None:
        hits = _normalize_entries(
            page_ids=page_ids,
            project_root=project_root,
            view_entries=view_entries,
        )
        if hits:
            st.session_state["view_entries_base"] = hits
        return hits
    hits = _resolve_view_entries(
        page_ids=page_ids,
        project_root=project_root,
        view_entries=None,
        prefer_session_entries=True,
    )
    if hits:
        st.session_state["view_entries_base"] = hits
    return hits


def _render_search_nav_scope_control(*, notebook_root: str | Path) -> str:
    """Segmented control for Search-result vs notebook-local Prev/Next."""
    current_scope = st.session_state.get("viewer_nav_scope", _NAV_SCOPE_SEARCH)
    default_label = _NAV_LABEL_BY_SCOPE.get(current_scope, _NAV_SCOPE_LABELS[0])
    choice = st.segmented_control(
        "Navigate",
        options=list(_NAV_SCOPE_LABELS),
        default=default_label,
        key="viewer_nav_scope_control",
        help=(
            "Search results: Prev/Next across matching hits. "
            "This notebook: Prev/Next through all pages in chronological order."
        ),
    )
    selected_label = choice or default_label
    new_scope = _NAV_SCOPE_BY_LABEL.get(selected_label, _NAV_SCOPE_SEARCH)
    if new_scope != current_scope:
        st.session_state["viewer_nav_scope"] = new_scope
        st.session_state["viewer_tag_filter"] = []
        if new_scope == _NAV_SCOPE_SEARCH:
            search_entries = st.session_state.get("view_entries_base") or []
            if isinstance(search_entries, list):
                snapped = _snap_page_to_search_scope(
                    st.session_state.get("view_page_id"),
                    search_entries,
                    notebook_root,
                )
                if snapped:
                    st.session_state["view_page_id"] = snapped
        st.rerun()
    return new_scope


def _page_number_to_index(page_number: int, total: int) -> int | None:
    """Map a 1-based page number to a 0-based index, or None if out of range."""
    if total < 1 or page_number < 1 or page_number > total:
        return None
    return page_number - 1


def _navigate_to_entry(entry: dict[str, str]) -> None:
    """Point the page viewer at a nav entry (may switch notebook root)."""
    st.session_state["view_page_id"] = entry["page_id"]
    st.session_state["root"] = entry["project_root"]
    st.session_state["pending_notebook_root"] = str(entry["project_root"])


def _scrub_viewer_after_page_delete(page_id: str, project_root: Path) -> None:
    """Drop the deleted page from Prev/Next nav and select a neighbour."""
    try:
        root_key = str(project_root.resolve())
    except OSError:
        root_key = str(project_root)

    entries = st.session_state.get("view_entries")
    if isinstance(entries, list) and entries:
        kept: list[dict[str, Any]] = []
        removed_idx: int | None = None
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            pid = str(entry.get("page_id") or "")
            raw_root = str(entry.get("project_root") or "")
            try:
                same_root = str(Path(raw_root).expanduser().resolve()) == root_key
            except OSError:
                same_root = raw_root == root_key
            if same_root and pid == page_id:
                removed_idx = i
                continue
            kept.append(entry)
        if removed_idx is None:
            # Fall through to page_ids scrub below.
            pass
        elif not kept:
            clear_page_viewer_state()
            return
        else:
            st.session_state["view_entries"] = kept
            st.session_state["view_page_ids"] = [
                str(e.get("page_id")) for e in kept if e.get("page_id")
            ]
            next_idx = min(removed_idx, len(kept) - 1)
            neighbour = kept[next_idx]
            _navigate_to_entry(
                {
                    "page_id": str(neighbour["page_id"]),
                    "project_root": str(neighbour["project_root"]),
                }
            )
            return

    page_ids = [
        pid for pid in (st.session_state.get("view_page_ids") or []) if pid and pid != page_id
    ]
    if not page_ids:
        clear_page_viewer_state()
        return
    st.session_state["view_page_ids"] = page_ids
    current = st.session_state.get("view_page_id")
    if current == page_id or current not in page_ids:
        st.session_state["view_page_id"] = page_ids[0]


@st.dialog("Delete page")
def _delete_page_dialog(
    *,
    page_id: str,
    projects: ProjectService,
    project_root: Path,
) -> None:
    st.markdown("Delete this page from the notebook?")
    st.caption(
        "Removes the page image, transcription, and related files from this "
        "notebook. This cannot be undone."
    )
    err = st.session_state.pop(f"pv_delete_error__{page_id}", None)
    if err:
        st.error(err)

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Cancel", key=f"pv_del_cancel__{page_id}", width="stretch", icon=ic.CANCEL
        ):
            st.rerun()
    with c2:
        if st.button(
            "Delete permanently",
            key=f"pv_del_ok__{page_id}",
            type="primary",
            width="stretch",
            icon=ic.DELETE,
        ):
            try:
                projects.delete_page(page_id)
            except (ProjectError, JobConflictError, TranscribeError, OSError) as exc:
                st.session_state[f"pv_delete_error__{page_id}"] = str(exc)
                st.session_state[f"pv_delete_pending__{page_id}"] = True
                st.rerun()
                return
            bump_archive_generation(build_runtime_paths())
            _scrub_viewer_after_page_delete(page_id, project_root)
            st.toast("Page deleted")
            st.rerun()


def _normalize_entries(
    *,
    page_ids: list[str] | None,
    project_root: str | Path | None,
    view_entries: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    if view_entries:
        out: list[dict[str, str]] = []
        for e in view_entries:
            pid = str(e.get("page_id") or "")
            root = str(e.get("project_root") or project_root or "")
            if pid and root:
                out.append({"page_id": pid, "project_root": root})
        return out
    root = str(project_root or "")
    return [{"page_id": pid, "project_root": root} for pid in (page_ids or []) if pid and root]


def _entry_root_exists(root: str | Path) -> bool:
    try:
        return (Path(root).expanduser() / "project.json").is_file()
    except OSError:
        return False


def _filter_existing_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop nav entries whose notebook was deleted or never had a manifest."""
    return [e for e in entries if _entry_root_exists(e["project_root"])]


def _page_tags_for_entries(entries: list[dict[str, str]]) -> dict[str, list[str]]:
    """Load page tag assignments for viewer entries (one project load per root)."""
    out: dict[str, list[str]] = {}
    by_root: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("page_id") or "")
        root = str(entry.get("project_root") or "")
        if not pid or not root:
            continue
        by_root.setdefault(root, []).append(pid)
    for root, page_ids in by_root.items():
        wanted = set(page_ids)
        try:
            svc = ProjectService(
                open_project_paths(Path(root)), clock=SystemClock(), ids=UuidGenerator()
            )
            project = svc.load(reconcile=False)
        except Exception:  # noqa: BLE001 — skip unreadable notebooks
            continue
        for page in project.pages:
            if page.page_id in wanted:
                out[page.page_id] = list(page.tags)
    return out


def _resolve_view_entries(
    *,
    page_ids: list[str] | None,
    project_root: str | Path | None,
    view_entries: list[dict[str, Any]] | None,
    prefer_session_entries: bool,
) -> list[dict[str, str]]:
    """Build the Prev/Next list without letting deleted notebooks stick around.

    Explicit ``view_entries`` (Archive/Search cross-notebook nav) win when passed.
    Explicit ``page_ids`` from Review/workflow rebuild for the active project and
    ignore stale session entries from a previous notebook.
    """
    if view_entries is not None:
        entries = _normalize_entries(
            page_ids=page_ids,
            project_root=project_root,
            view_entries=view_entries,
        )
    elif page_ids is not None:
        entries = _normalize_entries(
            page_ids=page_ids,
            project_root=project_root,
            view_entries=None,
        )
    elif prefer_session_entries:
        raw = st.session_state.get("view_entries")
        entries = (
            _normalize_entries(
                page_ids=None,
                project_root=project_root,
                view_entries=raw,
            )
            if raw
            else []
        )
        if not entries:
            entries = _normalize_entries(
                page_ids=st.session_state.get("view_page_ids"),
                project_root=project_root,
                view_entries=None,
            )
    else:
        entries = []

    entries = _filter_existing_entries(entries)
    if entries:
        return entries

    # Last resort: active project pages only.
    return _filter_existing_entries(
        _normalize_entries(
            page_ids=page_ids or st.session_state.get("view_page_ids"),
            project_root=project_root,
            view_entries=None,
        )
    )


def render_page_viewer(
    *,
    paths: ProjectPaths | None = None,
    projects: ProjectService | None = None,
    project: Project | None = None,
    page_id: str,
    page_ids: list[str] | None = None,
    highlight_query: str = "",
    back_label: str = "Back",
    show_back: bool = True,
    view_entries: list[dict[str, Any]] | None = None,
    presentation: str = "edit",
) -> Project | None:
    """Render scan + OCR + metadata for one page.

    When ``view_entries`` spans multiple notebooks, Prev/Next switches project roots.
    ``presentation="read"`` hides mutating controls (Reading mode).
    """
    read_only = presentation == "read"
    search_context = _is_search_reading_context(read_only=read_only)
    nav_scope = (
        st.session_state.get("viewer_nav_scope", _NAV_SCOPE_SEARCH)
        if search_context
        else _NAV_SCOPE_SEARCH
    )
    active_root = str(paths.root) if paths is not None else str(st.session_state.get("root") or "")

    search_hits: list[dict[str, str]] | None = None
    scoped_view_entries: list[dict[str, Any]] | None = view_entries
    if search_context:
        search_hits = _search_hit_entries(
            view_entries=view_entries,
            page_ids=page_ids,
            project_root=active_root,
        )
        if nav_scope == _NAV_SCOPE_NOTEBOOK:
            bootstrap_root = st.session_state.get("root") or active_root
            if bootstrap_root:
                bootstrap_paths = open_project_paths(Path(bootstrap_root))
                bootstrap_projects = ProjectService(
                    bootstrap_paths, clock=SystemClock(), ids=UuidGenerator()
                )
                bootstrap_project = bootstrap_projects.load(reconcile=False)
                scoped_view_entries = notebook_view_entries(bootstrap_project, bootstrap_root)
                paths = bootstrap_paths
                projects = bootstrap_projects
                project = bootstrap_project
        else:
            scoped_view_entries = search_hits

    entries = _resolve_view_entries(
        page_ids=page_ids if not search_context else None,
        project_root=active_root,
        view_entries=scoped_view_entries if search_context else view_entries,
        prefer_session_entries=not search_context,
    )
    if not entries:
        st.info("No pages in this context.")
        return project

    if search_context:
        baseline = (
            scoped_view_entries
            if nav_scope == _NAV_SCOPE_NOTEBOOK
            else (search_hits or entries)
        )
    elif view_entries is not None or page_ids is not None:
        baseline = entries
        st.session_state["view_entries_base"] = baseline
    else:
        raw_base = st.session_state.get("view_entries_base")
        baseline = raw_base if isinstance(raw_base, list) and raw_base else entries
        st.session_state["view_entries_base"] = baseline

    required_slugs = [
        str(s) for s in (st.session_state.get("viewer_tag_filter") or []) if str(s).strip()
    ]
    if required_slugs:
        from transcribe.tagging.kernel import constrain_entries

        page_tags = _page_tags_for_entries(baseline)
        entries = constrain_entries(baseline, page_tags, required_slugs)
        if not entries:
            st.info("No pages in this view have those tags.")
            if st.button("Clear tag filter", key="pv_clear_tag_filter_empty", icon=ic.RESET):
                st.session_state["viewer_tag_filter"] = []
                st.rerun()
            return project

    st.session_state["view_entries"] = entries
    page_ids_flat = [e["page_id"] for e in entries]
    if page_id not in page_ids_flat:
        page_id = page_ids_flat[0]
        st.session_state["view_page_id"] = page_id

    idx = page_ids_flat.index(page_id)
    entry = entries[idx]
    root = entry["project_root"]
    st.session_state["root"] = root
    st.session_state["view_page_id"] = page_id

    if (
        paths is None
        or projects is None
        or project is None
        or str(paths.root) != str(Path(root).resolve())
    ):
        paths = open_project_paths(Path(root))
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)

    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        st.error(f"Page {page_id[:8]}… not found in {project.title}")
        return project

    # Refresh unapproved suggestions (edit presentation only). Cover pages also
    # re-try while undated so they can inherit the first dated page after later
    # pages are filled.
    effective_cover_id = _reader_cover_page_id(project)
    needs_date_suggest = (not read_only) and (
        (not page.date_approved) or (page.date is None and page.page_id == effective_cover_id)
    )
    if needs_date_suggest:
        try:
            if projects.suggest_page_date(page.page_id):
                bump_archive_generation(build_runtime_paths())
            project = projects.load(reconcile=False)
            page = next((p for p in project.pages if p.page_id == page_id), page)
        except TranscribeError:
            pass

    render = project.renders[page.active_render_id]
    img_path = paths.resolve_contained(render.image_relpath)
    result = projects.load_page_result(page.page_id)

    if search_context:
        nav_scope = _render_search_nav_scope_control(notebook_root=paths.root)

    total = len(entries)
    if search_context and nav_scope == _NAV_SCOPE_NOTEBOOK:
        prev_help = "Previous page in notebook"
        next_help = "Next page in notebook"
        total_suffix = "pages"
    elif search_context:
        prev_help = "Previous matching hit"
        next_help = "Next matching hit"
        total_suffix = "hits"
    else:
        prev_help = "Previous page"
        next_help = "Next page"
        total_suffix = ""
    top = st.columns([1, 1, 2, 2, 1, 1])
    if show_back:
        if top[0].button(back_label, icon=ic.ARROW_BACK):
            st.session_state.pop("view_page_id", None)
            st.session_state.pop("view_page_ids", None)
            st.session_state.pop("view_entries", None)
            st.session_state.pop("view_entries_base", None)
            st.session_state.pop("viewer_tag_filter", None)
            st.session_state.pop("viewer_nav_scope", None)
            st.session_state.pop("viewer_nav_scope_control", None)
            st.session_state.pop("view_highlight", None)
            st.session_state["show_page_viewer"] = False
            return_mode = st.session_state.pop("page_return_mode", None)
            if return_mode:
                from transcribe.ui.navigation import apply_destination_to_session

                apply_destination_to_session(st.session_state, return_mode)
            st.rerun()
    else:
        top[0].write("")
    if top[1].button("", disabled=idx <= 0, help=prev_help, icon=ic.CHEVRON_LEFT):
        _navigate_to_entry(entries[idx - 1])
        st.rerun()
    top[2].markdown(
        f"**{project.title}**" + (f" · {page.date.format_display()}" if page.date else " · Undated")
    )
    with top[3]:
        with st.form("page_viewer_jump", border=False, clear_on_submit=False):
            jump_cols = st.columns([1.6, 0.9, 1.3])
            jump_to = jump_cols[0].number_input(
                "Page",
                min_value=1,
                max_value=max(total, 1),
                value=idx + 1,
                step=1,
                label_visibility="collapsed",
                help=f"Type a page number (1–{total}) and press Enter or Go",
            )
            jump_cols[1].markdown(f"/ {total}{f' {total_suffix}' if total_suffix else ''}")
            jumped = jump_cols[2].form_submit_button(
                "Go",
                key="pv_jump_go",
                use_container_width=True,
                icon=ic.ARROW_FORWARD,
            )
        if jumped:
            jump_idx = _page_number_to_index(int(jump_to), total)
            if jump_idx is not None and jump_idx != idx:
                _navigate_to_entry(entries[jump_idx])
                st.rerun()
    if top[4].button("", disabled=idx >= total - 1, help=next_help, icon=ic.CHEVRON_RIGHT):
        _navigate_to_entry(entries[idx + 1])
        st.rerun()
    top[5].caption(f"`{page.page_id[:8]}…`")

    if read_only:
        review_row = st.columns([5, 1])
        with review_row[1]:
            if st.button(
                "Review",
                key=f"pv_to_review_{page.page_id}",
                help="Open Review to edit this page's date, text, and OCR.",
                width="stretch",
                icon=ic.RATE_REVIEW,
            ):
                from transcribe.ui.view_jumps import jump_to_review

                jump_to_review(
                    page.page_id,
                    project=project,
                    project_root=paths.root,
                )

    from transcribe.services.tags import TagService
    from transcribe.tagging.kernel import display_tag, normalize_slugs
    from transcribe.ui.tag_pills import render_clickable_pills, render_tag_chips

    tag_svc = TagService()
    catalog = tag_svc.load_catalog()
    if project.tags:
        st.caption("Notebook")
        render_tag_chips(project.tags, catalog)

    required_slugs = [
        str(s) for s in (st.session_state.get("viewer_tag_filter") or []) if str(s).strip()
    ]
    if required_slugs:
        filt_cols = st.columns([6, 2])
        with filt_cols[0]:
            labels = ", ".join(display_tag(catalog, s).label for s in required_slugs)
            st.caption(f"Showing pages tagged: {labels}")
        if filt_cols[1].button("Clear tag filter", key="pv_clear_tag_filter", icon=ic.RESET):
            st.session_state["viewer_tag_filter"] = []
            st.rerun()

    page_tag_slugs = list(page.tags)
    baseline_entries = st.session_state.get("view_entries_base") or entries
    set_tags: list[str] = []
    if isinstance(baseline_entries, list):
        page_tags_map = _page_tags_for_entries(
            [e for e in baseline_entries if isinstance(e, dict) and e.get("page_id")]
        )
        seen_set: set[str] = set()
        for tags in page_tags_map.values():
            for slug in tags:
                if slug not in seen_set:
                    seen_set.add(slug)
                    set_tags.append(slug)
    pill_source = page_tag_slugs or set_tags
    extra = [s for s in required_slugs if s not in pill_source]
    clicked = render_clickable_pills(
        [*pill_source, *extra],
        catalog=catalog,
        selected=required_slugs,
        key_prefix=f"pv_tag_{page.page_id[:8]}",
    )
    if clicked:
        current = list(normalize_slugs(required_slugs))
        if clicked in current:
            current = [s for s in current if s != clicked]
        else:
            current.append(clicked)
        st.session_state["viewer_tag_filter"] = current
        st.rerun()

    if not read_only:
        try:
            from transcribe.detection.api import DetectionService
            from transcribe.ui.detection_tag_review import render_page_detection_tag_row

            det_svc = DetectionService(projects)
            page_findings = det_svc.findings_for_page(page.page_id)
            if page_findings:
                st.caption("Detections")
                for f in page_findings[:8]:
                    render_page_detection_tag_row(
                        det_svc=det_svc,
                        finding=f,
                        page_id=page.page_id,
                        key_prefix="pv",
                    )
        except Exception:  # noqa: BLE001 — optional surface; never break viewer
            pass
    else:
        try:
            from transcribe.detection.api import DetectionService

            det_svc = DetectionService(projects)
            page_findings = det_svc.findings_for_page(page.page_id)
            if page_findings:
                labels = [
                    f"{f.finding_type} · {f.confidence:.0%} · {f.review_status}"
                    for f in page_findings[:8]
                ]
                st.caption("Detections: " + " · ".join(labels))
        except Exception:  # noqa: BLE001
            pass

    compare_layout = (not read_only) and _shows_compare_attempts(result)
    if compare_layout:
        # Prefer/Promote is the job; scan is reference — narrower + collapsible.
        left, right = st.columns([2, 3])
    else:
        left, right = st.columns([3, 2])

    def _render_scan_and_metrics(*, image_width: int | str) -> None:
        st.image(str(img_path), width=image_width)
        # Reader cover pages are outside page-metrics, including first-page fallback.
        if page.page_id == _reader_cover_page_id(project):
            return
        try:
            from transcribe.ui.page_metrics_view import (
                ensure_page_metrics,
                render_page_metrics_strip,
            )

            metrics_doc = ensure_page_metrics(projects, project)
            row = metrics_doc.row_for_page(page.page_id) if metrics_doc else None
            render_page_metrics_strip(row)
        except Exception:  # noqa: BLE001 — optional surface; never break viewer
            pass

    with left:
        if compare_layout:
            with st.expander(
                "Page scan",
                expanded=True,
                key=f"pv_scan_{page.page_id}",
            ):
                _render_scan_and_metrics(image_width=_COMPARE_SCAN_IMAGE_WIDTH_PX)
        else:
            _render_scan_and_metrics(image_width="stretch")
    with right:
        status = result.status if result else "pending"
        st.write(f"Status: **{status}**")
        attempt = result.active_attempt() if result else None
        model_label = _transcription_model_label(attempt)
        if model_label:
            render_caption_with_info(
                f"Transcription model: {model_label}",
                _transcription_model_help(attempt, model_label),
            )
        if attempt and attempt.cleanup is not None:
            cu = attempt.cleanup
            if cu.execution_status == "disabled":
                pass
            elif cu.acceptance_status == "applied":
                render_caption_with_info(
                    f"Cleanup: applied ({cu.mode}) via {cu.model_name or 'text model'}",
                    _cleanup_mode_help(cu),
                )
            elif cu.acceptance_status == "unchanged":
                body = f"Cleanup: unchanged ({cu.note or 'identical'}) — kept OCR text"
                if cu.mode:
                    render_caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.acceptance_status == "validator_rejected":
                body = f"Cleanup: validator rejected — {cu.note} (kept raw OCR)"
                if cu.mode:
                    render_caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.execution_status == "provider_failed":
                body = f"Cleanup: provider failed — {cu.note} (kept raw OCR)"
                if cu.mode:
                    render_caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.execution_status == "skipped_empty_source":
                st.caption("Cleanup: skipped empty OCR source")
            if cu.pre_cleanup_text is not None and not read_only:
                with st.expander("Pre-cleanup OCR text", expanded=False):
                    st.text(cu.pre_cleanup_text)

        if not read_only:
            _render_attempt_compare(
                projects=projects,
                project=project,
                page_id=page.page_id,
                result=result,
            )

        raw = attempt.raw_text if attempt else ""
        edited = result.edited_text if result else None
        if not read_only and edited is not None and attempt and attempt.raw_text is not None:
            st.caption("An edit is active. New OCR raw text is preserved separately.")
            if st.button("Use new transcription", icon=ic.PROMOTE):
                projects.adopt_raw_as_edit(page.page_id)
                bump_archive_generation(build_runtime_paths())
                st.rerun()
        preferred = result.preferred_attempt() if result else None
        if (
            not read_only
            and preferred is not None
            and attempt is not None
            and preferred.attempt_id != attempt.attempt_id
        ):
            st.caption(
                "Preferred attempt differs from active — Prefer mode may be "
                "`prefer_only`, or promote explicitly."
            )
            if st.button("Use preferred as transcription basis", icon=ic.CHECK):
                projects.set_active_attempt(page.page_id, preferred.attempt_id)
                bump_archive_generation(build_runtime_paths())
                st.rerun()
        default_text = edited if edited is not None else (raw or "")
        if highlight_query.strip() and default_text:
            with st.expander("Highlighted transcription", expanded=True):
                st.markdown(highlight_terms(default_text, highlight_query))
        if read_only:
            if default_text.strip():
                _render_transcription_plain(default_text)
            else:
                st.caption("No transcription text on this page.")
            if page.date is not None and not page.date_approved:
                st.caption("Date is suggested, not approved — Archive timeline still indexes it.")
        else:
            text = st.text_area("Transcription", value=default_text, height=320)
            if st.button("Save edit", icon=ic.SAVE):
                projects.save_user_edit(page.page_id, text)
                bump_archive_generation(build_runtime_paths())
                st.success("Saved")

            with st.expander("Re-run this page", expanded=False):
                st.caption("Force OCR on this page with the notebook’s current model settings.")
                if st.button(
                    "Re-run OCR on this page",
                    key=f"rerun_page_{page.page_id}",
                    icon=ic.REPLAY,
                ):
                    try:
                        from transcribe.services.job import build_coordinator

                        _paths, _projects, coord, _ingest = build_coordinator(
                            paths.root, clock=SystemClock(), ids=UuidGenerator()
                        )
                        coord.start(page_ids=[page.page_id], force=True)
                        st.session_state["_job_was_running"] = True
                        st.session_state["show_compare_after_job"] = page.page_id
                        st.success("Page OCR started")
                        st.rerun()
                    except (JobConflictError, TranscribeError) as exc:
                        st.error(str(exc))

            st.divider()
            st.caption("Page metadata")
            date_default = page.date.format_display() if page.date else ""
            date_in = st.text_input(
                "Date (YYYY, YYYY-MM, YYYY-MM-DD, DD/MM/YYYY, DD/MM/YY, YYMMDD, "
                "or Jan 2, 2018; ambiguous numerics are day/month; time ignored)",
                value=date_default,
                key=f"date_{page.page_id}",
            )
            if page.date is None:
                page_text = result.effective_text() if result else None
                if looks_like_unparsed_date_stamp(page_text):
                    st.caption("Possible date in text wasn't recognized — set manually")
            if page.date is not None and not page.date_approved:
                if page.date_source == DATE_SOURCE_EXTRACTED:
                    suggest_label = "Suggested from transcription — not yet approved"
                elif page.date_source == DATE_SOURCE_INHERITED:
                    suggest_label = "Carried from previous page — not yet approved"
                else:
                    suggest_label = "Suggested — not yet approved"
                regressions = projects.list_date_regressions(project)
                approve_all_help = format_approve_all_dates_help(regressions)
                confirm_key = f"pv_confirm_date_regressions_{page.page_id}"
                cap_col, ok_col, all_col, no_col = st.columns(
                    [8, 1, 1, 1], vertical_alignment="center"
                )
                with cap_col:
                    st.caption(suggest_label)
                with ok_col:
                    if st.button(
                        "",
                        key=f"date_approve_{page.page_id}",
                        help="Approve suggested date",
                        type="tertiary",
                        icon=ic.CHECK,
                    ):
                        try:
                            projects.approve_page_date(page.page_id, page.date)
                            bump_archive_generation(build_runtime_paths())
                            st.session_state.pop(f"date_{page.page_id}", None)
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                        except (ValueError, TranscribeError) as exc:
                            st.error(str(exc))
                with all_col:
                    if st.button(
                        "",
                        key=f"date_approve_all_{page.page_id}",
                        help=approve_all_help,
                        type="tertiary",
                        icon=ic.CHECK_ALL,
                    ):
                        try:
                            confirm = bool(st.session_state.get(confirm_key))
                            if regressions and not confirm:
                                st.session_state[confirm_key] = True
                                st.warning(
                                    f"{len(regressions)} date regression"
                                    f"{'s' if len(regressions) != 1 else ''} look "
                                    "suspicious. Click Approve all again to approve anyway."
                                )
                            else:
                                updated, approved_n, _regs = projects.approve_all_suggested_dates(
                                    confirm_regressions=True
                                )
                                bump_archive_generation(build_runtime_paths())
                                st.session_state.pop(confirm_key, None)
                                for p in updated.pages:
                                    st.session_state.pop(f"date_{p.page_id}", None)
                                if approved_n:
                                    st.toast(
                                        f"Approved {approved_n} date"
                                        f"{'s' if approved_n != 1 else ''}"
                                    )
                                st.rerun()
                        except (ValueError, TranscribeError) as exc:
                            st.error(str(exc))
                with no_col:
                    if st.button(
                        "",
                        key=f"date_ignore_{page.page_id}",
                        help="Ignore suggestion (clear date)",
                        type="tertiary",
                        icon=ic.CLOSE,
                    ):
                        try:
                            projects.approve_page_date(page.page_id, None)
                            bump_archive_generation(build_runtime_paths())
                            st.session_state.pop(f"date_{page.page_id}", None)
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                        except (ValueError, TranscribeError) as exc:
                            st.error(str(exc))
                if regressions:
                    preview = "; ".join(hit.format_display() for hit in regressions[:3])
                    extra = len(regressions) - 3
                    if extra > 0:
                        preview = f"{preview}; …and {extra} more"
                    st.caption(f"Suspicious date order: {preview}")
            else:
                st.session_state.pop(f"pv_confirm_date_regressions_{page.page_id}", None)
            from transcribe.ui.tag_pills import render_tag_assignment_editor

            selected_tags, new_tag_raw = render_tag_assignment_editor(
                current=page.tags,
                catalog=catalog,
                key_prefix=f"tags_{page.page_id}",
            )
            if st.button("Save metadata", icon=ic.SAVE):
                try:
                    new_date = parse_date_input(date_in)
                    project, _date_changed = projects.approve_page_date(page.page_id, new_date)
                    combined = list(selected_tags)
                    combined.extend(t for t in new_tag_raw.split(",") if t.strip())
                    project = tag_svc.assign_page(projects, page.page_id, combined)
                    bump_archive_generation(build_runtime_paths())
                    st.success("Metadata saved")
                    st.rerun()
                except (ValueError, TranscribeError) as exc:
                    st.error(str(exc))

            thumbs = ThumbnailService(paths)
            if st.button("Set as notebook cover", icon=ic.MENU_BOOK):
                try:
                    from transcribe.ui.action_menus.nav import viewer_page_ids

                    project = projects.update_notebook_metadata(cover_page_id=page.page_id)
                    thumbs.ensure_thumb(project, page.page_id)
                    bump_archive_generation(build_runtime_paths())
                    ordered = viewer_page_ids(project)
                    root = str(paths.root)
                    entries = st.session_state.get("view_entries") or []
                    same_notebook = bool(entries) and all(
                        str(e.get("project_root") or "") == root for e in entries
                    )
                    if same_notebook or not entries:
                        st.session_state["view_page_ids"] = ordered
                        st.session_state["view_entries"] = [
                            {"page_id": pid, "project_root": root} for pid in ordered
                        ]
                    st.success("Cover updated")
                    st.rerun()
                except TranscribeError as exc:
                    st.error(str(exc))

            pending_delete = f"pv_delete_pending__{page.page_id}"
            if st.session_state.pop(pending_delete, False):
                _delete_page_dialog(
                    page_id=page.page_id,
                    projects=projects,
                    project_root=paths.root,
                )
            if st.button("Delete page", icon=ic.DELETE):
                if len(project.pages) <= 1:
                    st.error("Cannot delete the last page; delete the notebook instead.")
                else:
                    st.session_state[pending_delete] = True
                    st.rerun()

    if read_only:
        by_root = dict(st.session_state.get("reading_page_by_root") or {})
        by_root[str(paths.root)] = page.page_id
        st.session_state["reading_page_by_root"] = by_root

    return project


def open_page_context(
    *,
    page_id: str,
    page_ids: list[str],
    project_root: str | Path,
    highlight: str = "",
    return_mode: str | None = None,
    view_entries: list[dict[str, Any]] | None = None,
) -> None:
    entries = _normalize_entries(
        page_ids=page_ids,
        project_root=project_root,
        view_entries=view_entries,
    )
    st.session_state["root"] = str(project_root)
    st.session_state["pending_notebook_root"] = str(project_root)
    st.session_state["view_page_id"] = page_id
    st.session_state["view_page_ids"] = [e["page_id"] for e in entries]
    st.session_state["view_entries"] = entries
    st.session_state["view_entries_base"] = entries
    st.session_state["viewer_tag_filter"] = []
    st.session_state["view_highlight"] = highlight
    st.session_state["show_page_viewer"] = True
    if return_mode:
        st.session_state["page_return_mode"] = return_mode
    if return_mode == "Search":
        st.session_state["viewer_nav_scope"] = _NAV_SCOPE_SEARCH
        st.session_state.pop("viewer_nav_scope_control", None)
