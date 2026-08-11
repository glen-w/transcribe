"""Canonical page viewer shared by Archive, Search, and Workflow."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.domain.dates import (
    DATE_SOURCE_EXTRACTED,
    DATE_SOURCE_INHERITED,
    normalize_tags,
    parse_date_input,
)
from transcribe.domain.models import CleanupRecord, OCRAttempt, Project
from transcribe.errors import TranscribeError
from transcribe.paths import ProjectPaths
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import bump_archive_generation, highlight_terms
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService

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
        parts.append(
            "Identity unverified — fingerprint skip is disabled for this model tag."
        )
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


def _caption_with_info(body: str, help_text: str) -> None:
    """Caption line with a hover `(i)` tooltip (no click / no rerun)."""
    tip = html.escape(help_text, quote=True)
    body_esc = html.escape(body)
    st.markdown(
        f'<p style="font-size:0.875rem;color:var(--text-color);opacity:0.6;'
        f'margin:0 0 0.35rem 0;">{body_esc} '
        f'<span title="{tip}" style="cursor:help;opacity:0.9;user-select:none;" '
        f'aria-label="More info">(i)</span></p>',
        unsafe_allow_html=True,
    )


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
) -> Project | None:
    """Render scan + OCR + metadata for one page.

    When ``view_entries`` spans multiple notebooks, Prev/Next switches project roots.
    """
    active_root = (
        str(paths.root)
        if paths is not None
        else str(st.session_state.get("root") or "")
    )
    entries = _resolve_view_entries(
        page_ids=page_ids,
        project_root=active_root,
        view_entries=view_entries,
        prefer_session_entries=True,
    )
    if not entries:
        st.info("No pages in this context.")
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

    if paths is None or projects is None or project is None or str(paths.root) != str(Path(root).resolve()):
        paths = open_project_paths(Path(root))
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)

    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        st.error(f"Page {page_id[:8]}… not found in {project.title}")
        return project

    # Refresh unapproved suggestions. Cover pages also re-try while undated so they
    # can inherit the first dated page after later pages are filled.
    effective_cover_id = project.cover_page_id or (
        project.pages[0].page_id if project.pages else None
    )
    needs_date_suggest = (not page.date_approved) or (
        page.date is None and page.page_id == effective_cover_id
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

    total = len(entries)
    top = st.columns([1, 1, 2.2, 1.4, 1, 1])
    if show_back:
        if top[0].button(back_label):
            st.session_state.pop("view_page_id", None)
            st.session_state.pop("view_page_ids", None)
            st.session_state.pop("view_entries", None)
            st.session_state.pop("view_highlight", None)
            st.session_state["show_page_viewer"] = False
            return_mode = st.session_state.pop("page_return_mode", None)
            if return_mode:
                st.session_state["ui_mode"] = return_mode
            st.rerun()
    else:
        top[0].write("")
    if top[1].button("←", disabled=idx <= 0, help="Previous page"):
        _navigate_to_entry(entries[idx - 1])
        st.rerun()
    top[2].markdown(
        f"**{project.title}**"
        + (f" · {page.date.format_display()}" if page.date else " · Undated")
    )
    with top[3]:
        with st.form("page_viewer_jump", border=False, clear_on_submit=False):
            jump_cols = st.columns([2.2, 1.4, 1.2])
            jump_to = jump_cols[0].number_input(
                "Page",
                min_value=1,
                max_value=max(total, 1),
                value=idx + 1,
                step=1,
                label_visibility="collapsed",
                help=f"Type a page number (1–{total}) and press Enter or Go",
            )
            jump_cols[1].markdown(f"/ {total}")
            jumped = jump_cols[2].form_submit_button("Go")
        if jumped:
            jump_idx = _page_number_to_index(int(jump_to), total)
            if jump_idx is not None and jump_idx != idx:
                _navigate_to_entry(entries[jump_idx])
                st.rerun()
    if top[4].button("→", disabled=idx >= total - 1, help="Next page"):
        _navigate_to_entry(entries[idx + 1])
        st.rerun()
    top[5].caption(f"`{page.page_id[:8]}…`")

    if page.tags:
        st.caption("Tags: " + ", ".join(page.tags))

    try:
        from transcribe.detection.api import DetectionService

        det_svc = DetectionService(projects)
        page_findings = det_svc.findings_for_page(page.page_id)
        if page_findings:
            st.caption("Detections")
            for f in page_findings[:8]:
                fresh = det_svc.freshness(f.detector_id)
                stale = "" if fresh == "ok" else f" · {fresh}"
                cols = st.columns([6, 1, 1])
                cols[0].write(
                    f"{f.finding_type} · {f.confidence:.0%} · {f.review_status}{stale}"
                )
                if cols[1].button("✓", key=f"pv_ap_{f.finding_id}", help="Approve"):
                    det_svc.set_review_status(f.detector_id, f.finding_id, "approved")
                    st.rerun()
                if cols[2].button("✗", key=f"pv_rj_{f.finding_id}", help="Reject"):
                    det_svc.set_review_status(f.detector_id, f.finding_id, "rejected")
                    st.rerun()
    except Exception:  # noqa: BLE001 — optional surface; never break viewer
        pass

    left, right = st.columns([3, 2])
    with left:
        st.image(str(img_path), width="stretch")
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
    with right:
        status = result.status if result else "pending"
        st.write(f"Status: **{status}**")
        attempt = result.active_attempt() if result else None
        model_label = _transcription_model_label(attempt)
        if model_label:
            _caption_with_info(
                f"Transcription model: {model_label}",
                _transcription_model_help(attempt, model_label),
            )
        if attempt and attempt.cleanup is not None:
            cu = attempt.cleanup
            if cu.execution_status == "disabled":
                pass
            elif cu.acceptance_status == "applied":
                _caption_with_info(
                    f"Cleanup: applied ({cu.mode}) via {cu.model_name or 'text model'}",
                    _cleanup_mode_help(cu),
                )
            elif cu.acceptance_status == "unchanged":
                body = (
                    f"Cleanup: unchanged ({cu.note or 'identical'}) — kept OCR text"
                )
                if cu.mode:
                    _caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.acceptance_status == "validator_rejected":
                body = f"Cleanup: validator rejected — {cu.note} (kept raw OCR)"
                if cu.mode:
                    _caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.execution_status == "provider_failed":
                body = f"Cleanup: provider failed — {cu.note} (kept raw OCR)"
                if cu.mode:
                    _caption_with_info(body, _cleanup_mode_help(cu))
                else:
                    st.caption(body)
            elif cu.execution_status == "skipped_empty_source":
                st.caption("Cleanup: skipped empty OCR source")
            if cu.pre_cleanup_text is not None:
                with st.expander("Pre-cleanup OCR text", expanded=False):
                    st.text(cu.pre_cleanup_text)
        raw = attempt.raw_text if attempt else ""
        edited = result.edited_text if result else None
        if edited is not None and attempt and attempt.raw_text is not None:
            st.caption("An edit is active. New OCR raw text is preserved separately.")
            if st.button("Use new transcription"):
                projects.adopt_raw_as_edit(page.page_id)
                bump_archive_generation(build_runtime_paths())
                st.rerun()
        default_text = edited if edited is not None else (raw or "")
        if highlight_query.strip() and default_text:
            with st.expander("Highlighted transcription", expanded=True):
                st.markdown(highlight_terms(default_text, highlight_query))
        text = st.text_area("Transcription", value=default_text, height=320)
        if st.button("Save edit"):
            projects.save_user_edit(page.page_id, text)
            bump_archive_generation(build_runtime_paths())
            st.success("Saved")

        st.divider()
        st.caption("Page metadata")
        date_default = page.date.format_display() if page.date else ""
        date_in = st.text_input(
            "Date (YYYY, YYYY-MM, YYYY-MM-DD, DD/MM/YYYY, or YYMMDD; time ignored)",
            value=date_default,
            key=f"date_{page.page_id}",
        )
        if page.date is not None and not page.date_approved:
            if page.date_source == DATE_SOURCE_EXTRACTED:
                suggest_label = "Suggested from transcription — not yet approved"
            elif page.date_source == DATE_SOURCE_INHERITED:
                suggest_label = "Carried from previous page — not yet approved"
            else:
                suggest_label = "Suggested — not yet approved"
            cap_col, ok_col, no_col = st.columns([8, 1, 1], vertical_alignment="center")
            with cap_col:
                st.caption(suggest_label)
            with ok_col:
                if st.button(
                    "✓",
                    key=f"date_approve_{page.page_id}",
                    help="Approve suggested date",
                    type="tertiary",
                ):
                    try:
                        projects.approve_page_date(page.page_id, page.date)
                        bump_archive_generation(build_runtime_paths())
                        st.session_state.pop(f"date_{page.page_id}", None)
                        st.rerun()
                    except (ValueError, TranscribeError) as exc:
                        st.error(str(exc))
            with no_col:
                if st.button(
                    "✕",
                    key=f"date_ignore_{page.page_id}",
                    help="Ignore suggestion (clear date)",
                    type="tertiary",
                ):
                    try:
                        projects.approve_page_date(page.page_id, None)
                        bump_archive_generation(build_runtime_paths())
                        st.session_state.pop(f"date_{page.page_id}", None)
                        st.rerun()
                    except (ValueError, TranscribeError) as exc:
                        st.error(str(exc))
        tags_in = st.text_input(
            "Tags (comma-separated)",
            value=", ".join(page.tags),
            key=f"tags_{page.page_id}",
        )
        if st.button("Save metadata"):
            try:
                new_date = parse_date_input(date_in)
                project, date_changed = projects.approve_page_date(page.page_id, new_date)
                project = projects.update_page_metadata(
                    page.page_id,
                    tags=normalize_tags([t for t in tags_in.split(",")]),
                )
                if date_changed:
                    bump_archive_generation(build_runtime_paths())
                else:
                    # tags may have changed; bump so archive tag filters refresh
                    bump_archive_generation(build_runtime_paths())
                st.success("Metadata saved")
                st.rerun()
            except (ValueError, TranscribeError) as exc:
                st.error(str(exc))

        thumbs = ThumbnailService(paths)
        if st.button("Set as notebook cover"):
            try:
                project = projects.update_notebook_metadata(cover_page_id=page.page_id)
                thumbs.ensure_thumb(project, page.page_id)
                bump_archive_generation(build_runtime_paths())
                st.success("Cover updated")
            except TranscribeError as exc:
                st.error(str(exc))

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
    st.session_state["view_highlight"] = highlight
    st.session_state["show_page_viewer"] = True
    if return_mode:
        st.session_state["page_return_mode"] = return_mode
