"""Purpose-built OCR Review workbench (scan + transcription + disagreements)."""

from __future__ import annotations

import streamlit as st
from PIL import Image

from transcribe.domain.dates import (
    DATE_SOURCE_EXTRACTED,
    DATE_SOURCE_INHERITED,
    format_approve_all_dates_help,
    looks_like_unparsed_date_stamp,
    parse_date_input,
)
from transcribe.domain.models import DEFAULT_PREFER_MODE, PREFER_MODES, PageResult, Project
from transcribe.errors import JobConflictError, ProjectError, TranscribeError
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.paths import ProjectPaths
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import bump_archive_generation
from transcribe.services.ocr_alignment import (
    AlignmentResult,
    align_ocr,
    apply_region_variant,
    first_unresolved_index,
    grouped_source_variants,
    is_whitespace_only_change,
    next_unresolved_index,
)
from transcribe.services.ocr_composite_state import (
    current_composite_attempt,
    merge_input_vision_attempts,
    seed_editor_text,
    stale_composite_attempts,
)
from transcribe.services.project import ProjectService
from transcribe.services.review_signals import build_review_signals
from transcribe.services.thumbnails import ThumbnailService
from transcribe.ui.components.info_tooltip import widget_help
from transcribe.ui import icons as ic
from transcribe.ui.page_viewer import (
    _delete_page_dialog,
    _navigate_to_entry,
    _page_number_to_index,
    _transcription_model_label,
)

_ZOOM_CYCLE = ("fit_page", "fit_width", "700")
_ZOOM_WIDTH = {"fit_page": 560, "fit_width": "stretch", "700": 700}
_ZOOM_CYCLE_HELP = "Cycle zoom level (fit page, fit width, 700px)"

_SAVE_TRANSCRIPTION = "Save transcription"
_SAVE_MARK_REVIEWED = "Save + Mark reviewed"
_SAVE_OCR_SETTINGS = "Save OCR settings"
_SAVE_DATE = "Save date"
_SAVE_TAGS = "Save tags"


def _attempt_label(attempt) -> str:
    if (attempt.attempt_kind or "vision") == "composite":
        return "Merged draft"
    name = _transcription_model_label(attempt)
    return name or attempt.attempt_id[:8]


def _inject_review_hotkeys() -> None:
    st.iframe(
        f"""
<script>
(function () {{
  const parent = window.parent;
  if (!parent) return;
  if (parent.__txReviewHotkeysBound) return;
  parent.__txReviewHotkeysBound = true;
  const saveTranscription = {_SAVE_TRANSCRIPTION!r};
  const saveMarkReviewed = {_SAVE_MARK_REVIEWED!r};
  const zoomHelp = {_ZOOM_CYCLE_HELP!r};
  function clickLabel(label) {{
    const buttons = parent.document.querySelectorAll("button");
    for (const b of buttons) {{
      if ((b.innerText || "").trim() === label) {{
        b.click();
        return true;
      }}
    }}
    return false;
  }}
  function clickAriaLabel(label) {{
    const buttons = parent.document.querySelectorAll("button");
    for (const b of buttons) {{
      if ((b.getAttribute("aria-label") || "").trim() === label) {{
        b.click();
        return true;
      }}
    }}
    return false;
  }}
  function reviewAlive() {{
    return Array.from(parent.document.querySelectorAll("button")).some(
      (b) => (b.innerText || "").trim() === saveTranscription
    );
  }}
  parent.document.addEventListener(
    "keydown",
    function (e) {{
      if (!reviewAlive()) return;
      const t = e.target;
      const tag = ((t && t.tagName) || "").toLowerCase();
      const typing =
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        (t && t.isContentEditable);
      const saveCombo = (e.metaKey || e.ctrlKey) && (e.key === "s" || e.key === "S");
      if (typing && !saveCombo) return;
      if (saveCombo) {{
        e.preventDefault();
        clickLabel(saveTranscription);
        return;
      }}
      if (typing) return;
      if (e.key === "ArrowLeft") {{ e.preventDefault(); clickAriaLabel("Previous page"); }}
      else if (e.key === "ArrowRight") {{ e.preventDefault(); clickAriaLabel("Next page"); }}
      else if (e.key === "j" || e.key === "J") {{ clickLabel("Next disagreement"); }}
      else if (e.key === "k" || e.key === "K") {{ clickLabel("Previous disagreement"); }}
      else if (e.key === "1") {{ clickLabel("Use 1"); }}
      else if (e.key === "2") {{ clickLabel("Use 2"); }}
      else if (e.key === "3") {{ clickLabel("Use 3"); }}
      else if (e.key === "r" || e.key === "R") {{ clickLabel(saveMarkReviewed); }}
      else if (e.key === "z" || e.key === "Z") {{ clickAriaLabel(zoomHelp); }}
    }},
    true
  );
}})();
</script>
        """,
        height=1,
    )


def _ensure_buffer(page_id: str, result: PageResult) -> None:
    buf_key = f"rw_buf_{page_id}"
    if buf_key not in st.session_state:
        text = seed_editor_text(result)
        st.session_state[buf_key] = text
        st.session_state[f"rw_gen_{page_id}"] = 0
        st.session_state[f"rw_saved_{page_id}"] = result.effective_text() or text
        st.session_state[f"rw_origin_{page_id}"] = result.effective_text_origin
        st.session_state[f"rw_resolved_{page_id}"] = set()
        st.session_state[f"rw_idx_{page_id}"] = 0
        st.session_state[f"rw_undo_{page_id}"] = []
        st.session_state[f"rw_zoom_{page_id}"] = "fit_page"
        st.session_state[f"rw_rot_{page_id}"] = 0


def _set_buffer(page_id: str, text: str, *, origin: str | None = None) -> None:
    st.session_state[f"rw_undo_{page_id}"] = st.session_state.get(f"rw_undo_{page_id}") or []
    st.session_state[f"rw_undo_{page_id}"].append(st.session_state.get(f"rw_buf_{page_id}") or "")
    st.session_state[f"rw_buf_{page_id}"] = text
    st.session_state[f"rw_gen_{page_id}"] = int(st.session_state.get(f"rw_gen_{page_id}") or 0) + 1
    if origin:
        st.session_state[f"rw_origin_{page_id}"] = origin


def _is_dirty(page_id: str) -> bool:
    return (st.session_state.get(f"rw_buf_{page_id}") or "") != (
        st.session_state.get(f"rw_saved_{page_id}") or ""
    )


def _render_page_scan_toolbar(page_id: str) -> None:
    """Compact icon toolbar centered above the page scan."""
    _, toolbar, _ = st.columns([1, 2, 1])
    with toolbar:
        c0, c1, c2, c3 = st.columns(4)
        with c0:
            if st.button(
                "",
                key=f"rw_fitp_{page_id}",
                icon=ic.CROP_FREE,
                type="tertiary",
                width="content",
                help=widget_help("Fit page"),
            ):
                st.session_state[f"rw_zoom_{page_id}"] = "fit_page"
                st.rerun()
        with c1:
            if st.button(
                "",
                key=f"rw_fitw_{page_id}",
                icon=ic.WIDTH_NORMAL,
                type="tertiary",
                width="content",
                help=widget_help("Fit width"),
            ):
                st.session_state[f"rw_zoom_{page_id}"] = "fit_width"
                st.rerun()
        with c2:
            if st.button(
                "",
                key=f"rw_zoom_btn_{page_id}",
                icon=ic.ZOOM_IN,
                type="tertiary",
                width="content",
                help=widget_help(_ZOOM_CYCLE_HELP),
            ):
                current_z = st.session_state.get(f"rw_zoom_{page_id}") or "fit_page"
                nxt = (
                    _ZOOM_CYCLE[(_ZOOM_CYCLE.index(current_z) + 1) % len(_ZOOM_CYCLE)]
                    if current_z in _ZOOM_CYCLE
                    else "fit_page"
                )
                st.session_state[f"rw_zoom_{page_id}"] = nxt
                st.rerun()
        with c3:
            if st.button(
                "",
                key=f"rw_rot_btn_{page_id}",
                icon=ic.ROTATE_RIGHT,
                type="tertiary",
                width="content",
                help=widget_help("Rotate 90° clockwise"),
            ):
                st.session_state[f"rw_rot_{page_id}"] = (
                    int(st.session_state.get(f"rw_rot_{page_id}") or 0) + 1
                ) % 4
                st.rerun()


def _align_for_result(result: PageResult, canonical: str) -> AlignmentResult | None:
    sources = {
        attempt.attempt_id: attempt.raw_text or ""
        for attempt in merge_input_vision_attempts(result)
    }
    if len(sources) < 2:
        return None
    current = current_composite_attempt(result)
    composite = current.raw_text if current is not None else None
    return align_ocr(sources, composite_candidate=composite, canonical_buffer=canonical)


def _provenance_line(
    *,
    result: PageResult,
    origin: str | None,
    dirty: bool,
) -> str:
    current = current_composite_attempt(result)
    active = result.active_attempt()
    if origin == "human_corrected":
        head = "Human corrected"
    elif origin == "human_selected":
        head = "Human selected"
    elif origin == "composite" or (
        current is not None and active is not None and active.attempt_id == current.attempt_id
    ):
        head = "Merged draft"
    elif active is not None and (active.attempt_kind or "vision") == "composite":
        head = "Merged draft (stale)"
    else:
        head = _attempt_label(active) if active else "No OCR yet"
    return f"{head} · {'unsaved changes' if dirty else 'saved'}"


def render_review_page(
    *,
    paths: ProjectPaths,
    projects: ProjectService,
    project: Project,
    page_id: str,
    page_ids: list[str],
    view_entries: list[dict[str, str]] | None = None,
) -> None:
    """Render the OCR comparison workbench for one page in the Review queue."""
    _inject_review_hotkeys()
    entries = view_entries or [{"page_id": pid, "project_root": str(paths.root)} for pid in page_ids]
    ids = [e["page_id"] for e in entries]
    if page_id not in ids:
        page_id = ids[0]
        st.session_state["view_page_id"] = page_id
    idx = ids.index(page_id)
    total = len(ids)

    try:
        projects.repair_review_validity(page_id)
        project = projects.load(reconcile=False)
    except (TranscribeError, ProjectError):
        pass

    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        st.error("Page not found in this notebook.")
        return
    render = project.renders[page.active_render_id]
    img_path = paths.resolve_contained(render.image_relpath)
    result = projects.load_page_result(page_id) or PageResult(page_id=page_id)
    _ensure_buffer(page_id, result)

    review_status = page.review_status or "unreviewed"
    date_label = page.date.format_display() if page.date else "Undated"
    chip = review_status.replace("_", " ")
    if review_status == "reviewed":
        chip = "✓ reviewed"
    elif review_status == "needs_attention":
        chip = "⚠ needs attention"

    nav = st.columns([1, 1, 2.4, 2.2, 1, 1.2])
    if nav[0].button(
        "",
        disabled=idx <= 0,
        help="Previous page",
        key="rw_prev_page",
        icon=ic.CHEVRON_LEFT,
    ):
        if _is_dirty(page_id):
            st.warning(
                "Unsaved changes on this page — Save first, or click Previous page again to discard."
            )
            if st.session_state.get("rw_force_leave") == page_id:
                st.session_state.pop("rw_force_leave", None)
                _navigate_to_entry(entries[idx - 1])
                st.session_state.pop(f"rw_buf_{page_id}", None)
                st.rerun()
            st.session_state["rw_force_leave"] = page_id
        else:
            _navigate_to_entry(entries[idx - 1])
            st.rerun()
    if nav[1].button(
        "",
        disabled=idx >= total - 1,
        help="Next page",
        key="rw_next_page",
        icon=ic.CHEVRON_RIGHT,
    ):
        if _is_dirty(page_id):
            st.warning(
                "Unsaved changes on this page — Save first, or click Next page again to discard."
            )
            if st.session_state.get("rw_force_leave") == page_id:
                st.session_state.pop("rw_force_leave", None)
                _navigate_to_entry(entries[idx + 1])
                st.session_state.pop(f"rw_buf_{page_id}", None)
                st.rerun()
            st.session_state["rw_force_leave"] = page_id
        else:
            _navigate_to_entry(entries[idx + 1])
            st.rerun()
    nav[2].markdown(f"**{project.title}** · {date_label}")
    with nav[3]:
        with st.form("rw_jump", border=False, clear_on_submit=False):
            jc = st.columns([1.6, 0.9, 1.3])
            jump_to = jc[0].number_input(
                "Page",
                min_value=1,
                max_value=max(total, 1),
                value=idx + 1,
                step=1,
                label_visibility="collapsed",
            )
            jc[1].markdown(f"/ {total}")
            if jc[2].form_submit_button(
                "Go",
                key="rw_jump_go",
                use_container_width=True,
                icon=ic.ARROW_FORWARD,
            ):
                jump_idx = _page_number_to_index(int(jump_to), total)
                if jump_idx is not None and jump_idx != idx:
                    _navigate_to_entry(entries[jump_idx])
                    st.rerun()
    nav[4].caption(chip)
    if page.date is not None and not page.date_approved:
        if nav[5].button(
            "Date",
            help="Approve suggested date",
            icon=ic.CHECK,
        ):
            try:
                projects.approve_page_date(page_id, page.date)
                bump_archive_generation(build_runtime_paths())
                st.rerun()
            except (ValueError, TranscribeError) as exc:
                st.error(str(exc))
    else:
        nav[5].write("")

    canonical = st.session_state[f"rw_buf_{page_id}"]
    dirty = _is_dirty(page_id)
    origin = st.session_state.get(f"rw_origin_{page_id}")
    alignment = _align_for_result(result, canonical)
    resolved: set[str] = set(st.session_state.get(f"rw_resolved_{page_id}") or set())
    remaining = 0
    if alignment is not None:
        remaining = sum(1 for r in alignment.regions if r.key not in resolved)
        sources = {
            a.attempt_id: a.raw_text or "" for a in merge_input_vision_attempts(result)
        }
        signals = build_review_signals(alignment, sources, remaining=remaining)
        warn = "⚠ " if alignment.source_disagreement_count or alignment.departure_count else ""
        st.caption(warn + signals.header_line())
        try:
            if result.source_disagreement_count != alignment.source_disagreement_count:
                projects.cache_alignment_signals(
                    page_id,
                    source_disagreement_count=alignment.source_disagreement_count,
                    agreement_ratio=alignment.agreement_ratio,
                )
        except TranscribeError:
            pass
        if alignment.source_disagreement_count == 0 and alignment.departure_count == 0:
            n = len(alignment.source_ids)
            st.caption(f"{n}/{n} source attempts agree")
    elif result.attempts:
        st.caption("Single OCR reading — no source disagreement to review.")

    left, right = st.columns([1, 1], gap="medium")
    with left:
        _render_page_scan_toolbar(page_id)
        st.markdown(
            """
<style>
div[data-testid="stImage"] img {
    max-height: 55vh;
    width: auto;
    max-width: 100%;
    object-fit: contain;
}
</style>
            """,
            unsafe_allow_html=True,
        )
        image = Image.open(img_path)
        rot = int(st.session_state.get(f"rw_rot_{page_id}") or 0)
        if rot:
            image = image.rotate(-90 * rot, expand=True)
        zoom = st.session_state.get(f"rw_zoom_{page_id}") or "fit_page"
        st.image(image, width=_ZOOM_WIDTH.get(zoom, 560))
        try:
            from transcribe.ui.page_metrics_view import (
                ensure_page_metrics,
                render_page_metrics_strip,
            )

            metrics_doc = ensure_page_metrics(projects, project)
            row = metrics_doc.row_for_page(page_id) if metrics_doc else None
            render_page_metrics_strip(row)
        except Exception:  # noqa: BLE001
            pass

    date_tab_label = "Date"
    if page.date is not None and not page.date_approved:
        date_tab_label = "Date ⚠"
    with right:
        tab_trans, tab_date, tab_tags, tab_other = st.tabs(
            ["Transcription", date_tab_label, "Tags", "Other"]
        )
        with tab_trans:
            st.caption(_provenance_line(result=result, origin=origin, dirty=dirty))
            gen = int(st.session_state.get(f"rw_gen_{page_id}") or 0)
            text = st.text_area(
                "Transcription",
                value=canonical,
                height=420,
                key=f"rw_ta_{page_id}_{gen}",
                label_visibility="collapsed",
            )
            if text != canonical:
                st.session_state[f"rw_buf_{page_id}"] = text
                saved = st.session_state.get(f"rw_saved_{page_id}") or ""
                if not is_whitespace_only_change(saved, text):
                    st.session_state[f"rw_origin_{page_id}"] = "human_corrected"
                canonical = text
                dirty = _is_dirty(page_id)
            act = st.columns([1.4, 1.6, 0.8, 0.8], gap="medium")
            if act[0].button(
                _SAVE_TRANSCRIPTION,
                type="primary",
                key=f"rw_save_{page_id}",
                icon=ic.SAVE,
            ):
                if _save_buffer(projects, page_id, mark_reviewed=False):
                    st.rerun()
            if act[1].button(
                _SAVE_MARK_REVIEWED,
                key=f"rw_save_rev_{page_id}",
                icon=ic.TASK_ALT,
            ):
                if _save_buffer(projects, page_id, mark_reviewed=True):
                    _advance_after_reviewed(entries, idx)
                    st.rerun()
            if act[2].button("Skip", key=f"rw_skip_{page_id}", icon=ic.SKIP):
                try:
                    projects.set_page_review_status(page_id, "skipped")
                except TranscribeError as exc:
                    st.error(str(exc))
                else:
                    _advance_after_reviewed(entries, idx)
                    st.rerun()
            if act[3].button(
                "Undo",
                disabled=not st.session_state.get(f"rw_undo_{page_id}"),
                key=f"rw_undo_btn_{page_id}",
                icon=ic.UNDO,
            ):
                stack = st.session_state.get(f"rw_undo_{page_id}") or []
                if stack:
                    st.session_state[f"rw_buf_{page_id}"] = stack.pop()
                    st.session_state[f"rw_gen_{page_id}"] = gen + 1
                    st.rerun()

            if result.edited_text is not None:
                if st.button(
                    "Restore OCR original",
                    key=f"rw_restore_{page_id}",
                    icon=ic.HISTORY,
                ):
                    projects.adopt_raw_as_edit(page_id)
                    bump_archive_generation(build_runtime_paths())
                    for key in list(st.session_state.keys()):
                        if isinstance(key, str) and key.startswith("rw_") and key.endswith(page_id):
                            st.session_state.pop(key, None)
                    st.rerun()

        with tab_date:
            _render_date_tab(projects, project, page, result)

        with tab_tags:
            _render_tags_tab(projects, page)

        with tab_other:
            _render_other_tab(paths, projects, project, page)

    _render_ocr_comparison_band(
        projects,
        project,
        page_id,
        result,
        alignment,
        resolved,
        canonical,
    )


def _render_ocr_comparison_band(
    projects: ProjectService,
    project: Project,
    page_id: str,
    result: PageResult,
    alignment: AlignmentResult | None,
    resolved: set[str],
    canonical: str,
) -> None:
    """Full-width OCR evidence and disagreement controls below scan + tabs."""
    vision = merge_input_vision_attempts(result)
    current = current_composite_attempt(result)
    if not vision and current is None and alignment is None:
        return
    st.divider()
    _render_evidence_strip(projects, project, page_id, result)
    if alignment is not None:
        _render_disagreement_panel(page_id, result, alignment, resolved, canonical)


def _save_buffer(projects: ProjectService, page_id: str, *, mark_reviewed: bool) -> bool:
    text = st.session_state.get(f"rw_buf_{page_id}") or ""
    origin = st.session_state.get(f"rw_origin_{page_id}")
    result = projects.load_page_result(page_id)
    effective = (result.effective_text() if result else None) or ""
    edited: str | None = text
    if result is not None and result.edited_text is None and text == effective:
        edited = None
    try:
        saved = projects.save_user_edit(
            page_id,
            edited,
            origin=origin,
            mark_reviewed=mark_reviewed,
        )
    except TranscribeError as exc:
        st.error(str(exc))
        return False
    bump_archive_generation(build_runtime_paths())
    st.session_state[f"rw_saved_{page_id}"] = saved.effective_text() or ""
    st.session_state[f"rw_buf_{page_id}"] = st.session_state[f"rw_saved_{page_id}"]
    st.toast("Reviewed" if mark_reviewed else "Saved")
    return True


def _advance_after_reviewed(entries: list[dict[str, str]], idx: int) -> None:
    if idx + 1 < len(entries):
        _navigate_to_entry(entries[idx + 1])
    st.session_state.pop("rw_force_leave", None)


def _render_evidence_strip(
    projects: ProjectService,
    project: Project,
    page_id: str,
    result: PageResult,
) -> None:
    vision = merge_input_vision_attempts(result)
    current = current_composite_attempt(result)
    stale = stale_composite_attempts(result)
    if not vision and current is None:
        return
    st.markdown("#### OCR evidence")
    options: list[str] = [a.attempt_id for a in vision]
    labels = {}
    for attempt in vision:
        role = []
        if result.active_attempt_id == attempt.attempt_id:
            role.append("Current")
        if result.preferred_attempt_id == attempt.attempt_id:
            role.append("Default")
        suffix = f" · {' · '.join(role)}" if role else ""
        labels[attempt.attempt_id] = f"{_attempt_label(attempt)}{suffix}"
    if current is not None:
        options.append(current.attempt_id)
        extra = " · Current" if result.active_attempt_id == current.attempt_id else ""
        labels[current.attempt_id] = f"Merged draft{extra}"
    selected = st.radio(
        "Attempt",
        options=options,
        format_func=lambda i: labels.get(i, i),
        horizontal=True,
        key=f"rw_att_{page_id}",
        label_visibility="collapsed",
    )
    act = st.columns([1.2, 1.2, 2.6], gap="medium")
    if act[0].button(
        "Use as current text",
        key=f"rw_use_{page_id}",
        icon=ic.CHECK_CIRCLE,
    ):
        try:
            prefer_mode = project.settings.prefer_mode if project.settings.prefer_mode in PREFER_MODES else DEFAULT_PREFER_MODE
            if prefer_mode == "prefer_is_promote":
                projects.set_preferred_attempt(page_id, selected, mode=prefer_mode)
            else:
                projects.set_active_attempt(page_id, selected)
            if result.edited_text is not None:
                projects.save_user_edit(page_id, None, origin=None)
            bump_archive_generation(build_runtime_paths())
            for key in (f"rw_buf_{page_id}", f"rw_gen_{page_id}", f"rw_saved_{page_id}", f"rw_origin_{page_id}"):
                st.session_state.pop(key, None)
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))
    chosen = result.attempt_by_id(selected)
    if chosen and act[1].button(
        "Copy into editor",
        key=f"rw_copy_{page_id}",
        icon=ic.COPY,
    ):
        _set_buffer(page_id, chosen.raw_text or "", origin="human_selected")
        st.rerun()
    with act[2]:
        with st.expander("Compare full text", expanded=False):
            if chosen:
                st.text(chosen.raw_text or "")
            if stale:
                st.caption(f"{len(stale)} previous merged draft(s) retained (stale).")
                for old in stale[:4]:
                    st.caption(f"stale {old.attempt_id[:8]} · {old.started_at}")


def _render_disagreement_panel(
    page_id: str,
    result: PageResult,
    alignment: AlignmentResult,
    resolved: set[str],
    canonical: str,
) -> None:
    regions = alignment.regions
    if not regions:
        return
    idx = int(st.session_state.get(f"rw_idx_{page_id}") or 0)
    idx = max(0, min(idx, len(regions) - 1))
    region = regions[idx]
    remaining = sum(1 for r in regions if r.key not in resolved)
    st.divider()
    kind = "Source disagreement" if region.kind == "source" else "Merged-draft departure"
    st.markdown(
        f"#### {kind} · {idx + 1}/{len(regions)} · line {region.line_hint}"
    )
    st.caption(
        f"{alignment.source_disagreement_count} OCR disagreements · "
        f"{len(resolved)} resolved · {remaining} remaining"
    )
    nav = st.columns([1.2, 1.2, 5.6], gap="medium")
    if nav[0].button(
        "Previous disagreement",
        key=f"rw_dprev_{page_id}",
        icon=ic.CHEVRON_LEFT,
    ):
        st.session_state[f"rw_idx_{page_id}"] = next_unresolved_index(
            regions, resolved, idx, direction=-1
        )
        st.rerun()
    if nav[1].button(
        "Next disagreement",
        key=f"rw_dnext_{page_id}",
        icon=ic.CHEVRON_RIGHT,
    ):
        st.session_state[f"rw_idx_{page_id}"] = next_unresolved_index(
            regions, resolved, idx, direction=1
        )
        st.rerun()

    if region.key in resolved:
        st.caption("Resolved in this session — underlying OCR evidence still disagrees.")

    groups = grouped_source_variants(region)
    variant_cols = st.columns(max(len(groups), 1), gap="medium")
    for col, (ids, display) in zip(variant_cols, groups):
        names = []
        for aid in ids:
            attempt = result.attempt_by_id(aid)
            names.append(_attempt_label(attempt) if attempt else aid[:8])
        with col:
            st.markdown(f"**{' + '.join(names)}**")
            st.markdown(escape_markdown_plain(display))
    if region.composite_variant:
        verb = "departs" if region.composite_departure else "recommends"
        st.caption(f"Merged draft {verb}: {escape_markdown_plain(region.composite_variant)}")

    chip_count = min(len(groups), 3) + (1 if region.composite_variant else 0) + 1
    chips = st.columns(chip_count, gap="medium")
    chip_i = 0
    for i, (_ids, display) in enumerate(groups[:3]):
        if chips[chip_i].button(
            f"Use {i + 1}",
            key=f"rw_usev_{page_id}_{region.key}_{i}",
            icon=ic.USE_VARIANT[i],
        ):
            _apply_region_choice(page_id, canonical, alignment, region, display, resolved)
        chip_i += 1
    if region.composite_variant:
        if chips[chip_i].button(
            "Use merged draft",
            key=f"rw_usecomp_{page_id}_{region.key}",
            icon=ic.MERGE,
        ):
            _apply_region_choice(
                page_id, canonical, alignment, region, region.composite_variant, resolved
            )
        chip_i += 1
    if chips[chip_i].button(
        "Type correction",
        key=f"rw_type_{page_id}_{region.key}",
        icon=ic.EDIT,
    ):
        resolved.add(region.key)
        st.session_state[f"rw_resolved_{page_id}"] = resolved
        st.session_state[f"rw_origin_{page_id}"] = "human_corrected"
        st.info("Edit the transcription above, then Save.")


def _apply_region_choice(
    page_id: str,
    canonical: str,
    alignment: AlignmentResult,
    region,
    display: str,
    resolved: set[str],
) -> None:
    patched = apply_region_variant(canonical, alignment, region, display)
    _set_buffer(page_id, patched, origin="human_selected")
    resolved.add(region.key)
    st.session_state[f"rw_resolved_{page_id}"] = resolved
    st.session_state[f"rw_idx_{page_id}"] = first_unresolved_index(
        alignment.regions, resolved, after_base_i1=region.base_i1
    )
    st.rerun()


def _render_ocr_settings(projects: ProjectService, project: Project, page_id: str) -> None:
    st.markdown("**OCR settings**")
    settings = project.settings
    prefer_mode = (
        settings.prefer_mode if settings.prefer_mode in PREFER_MODES else DEFAULT_PREFER_MODE
    )
    mode_labels = {
        "prefer_is_promote": "Notebook default = current text",
        "prefer_only": "Notebook default only (stats / fine-tune)",
        "prefer_promote_with_edit_gate": "Notebook default + current, with edit gate",
    }
    new_mode = st.selectbox(
        "When setting a notebook default",
        options=list(mode_labels.keys()),
        format_func=lambda m: mode_labels[m],
        index=list(mode_labels.keys()).index(prefer_mode),
        key=f"rw_prefer_{page_id}",
    )
    auto_comp = st.checkbox(
        "Seed transcription from merged draft after multipass",
        value=bool(settings.auto_activate_composite),
        key=f"rw_auto_{page_id}",
    )
    if st.button(
        _SAVE_OCR_SETTINGS,
        key=f"rw_save_ocr_{page_id}",
        icon=ic.SAVE,
    ):
        settings.prefer_mode = new_mode
        settings.auto_activate_composite = bool(auto_comp)
        projects.save_settings(project, settings)
        st.rerun()


def _render_date_tab(projects, project, page, result) -> None:
    date_default = page.date.format_display() if page.date else ""
    date_in = st.text_input(
        "Date",
        value=date_default,
        key=f"rw_date_{page.page_id}",
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
        confirm_key = f"rw_confirm_date_regressions_{page.page_id}"
        cap_col, ok_col, all_col, no_col = st.columns([8, 1, 1, 1], vertical_alignment="center")
        with cap_col:
            st.caption(suggest_label)
        with ok_col:
            if st.button(
                "",
                key=f"rw_date_approve_{page.page_id}",
                help="Approve suggested date",
                type="tertiary",
                icon=ic.CHECK,
            ):
                try:
                    projects.approve_page_date(page.page_id, page.date)
                    bump_archive_generation(build_runtime_paths())
                    st.session_state.pop(f"rw_date_{page.page_id}", None)
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                except (ValueError, TranscribeError) as exc:
                    st.error(str(exc))
        with all_col:
            if st.button(
                "",
                key=f"rw_date_approve_all_{page.page_id}",
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
                            st.session_state.pop(f"rw_date_{p.page_id}", None)
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
                key=f"rw_date_ignore_{page.page_id}",
                help="Ignore suggestion (clear date)",
                type="tertiary",
                icon=ic.CLOSE,
            ):
                try:
                    projects.approve_page_date(page.page_id, None)
                    bump_archive_generation(build_runtime_paths())
                    st.session_state.pop(f"rw_date_{page.page_id}", None)
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
        st.session_state.pop(f"rw_confirm_date_regressions_{page.page_id}", None)
    if st.button(
        _SAVE_DATE,
        key=f"rw_save_date_{page.page_id}",
        icon=ic.SAVE,
    ):
        try:
            new_date = parse_date_input(date_in)
            projects.approve_page_date(page.page_id, new_date)
            bump_archive_generation(build_runtime_paths())
            st.rerun()
        except (ValueError, TranscribeError) as exc:
            st.error(str(exc))


def _render_tags_tab(projects, page) -> None:
    from transcribe.services.tags import TagService
    from transcribe.ui.tag_pills import render_tag_assignment_editor

    tag_svc = TagService()
    catalog = tag_svc.load_catalog()
    selected_tags, new_tag_raw = render_tag_assignment_editor(
        current=page.tags,
        catalog=catalog,
        key_prefix=f"rw_tags_{page.page_id}",
    )
    if st.button(
        _SAVE_TAGS,
        key=f"rw_save_tags_{page.page_id}",
        icon=ic.SAVE,
    ):
        try:
            combined = list(selected_tags)
            combined.extend(t for t in new_tag_raw.split(",") if t.strip())
            tag_svc.assign_page(projects, page.page_id, combined)
            bump_archive_generation(build_runtime_paths())
            st.rerun()
        except (ValueError, TranscribeError) as exc:
            st.error(str(exc))


def _render_other_tab(paths, projects, project, page) -> None:
    thumbs = ThumbnailService(paths)
    if st.button(
        "Set as notebook cover",
        key=f"rw_cover_{page.page_id}",
        icon=ic.MENU_BOOK,
    ):
        try:
            from transcribe.ui.action_menus.nav import viewer_page_ids

            project = projects.update_notebook_metadata(cover_page_id=page.page_id)
            thumbs.ensure_thumb(project, page.page_id)
            bump_archive_generation(build_runtime_paths())
            ordered = viewer_page_ids(project)
            root = str(paths.root)
            st.session_state["view_page_ids"] = ordered
            st.session_state["view_entries"] = [
                {"page_id": pid, "project_root": root} for pid in ordered
            ]
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))

    _render_ocr_settings(projects, project, page.page_id)

    if st.button(
        "Re-run OCR on this page",
        key=f"rw_rerun_{page.page_id}",
        icon=ic.REPLAY,
    ):
        try:
            from transcribe.services.job import build_coordinator

            _paths, _projects, coord, _ingest = build_coordinator(
                paths.root, clock=SystemClock(), ids=UuidGenerator()
            )
            coord.start(page_ids=[page.page_id], force=True)
            st.session_state["_job_was_running"] = True
            st.success("Page OCR started")
            st.rerun()
        except (JobConflictError, TranscribeError) as exc:
            st.error(str(exc))

    st.divider()
    pending_delete = f"rw_delete_pending__{page.page_id}"
    if st.session_state.pop(pending_delete, False):
        _delete_page_dialog(
            page_id=page.page_id,
            projects=projects,
            project_root=paths.root,
        )
    if st.button(
        "Delete page",
        key=f"rw_del_{page.page_id}",
        icon=ic.DELETE,
    ):
        if len(project.pages) <= 1:
            st.error("Cannot delete the last page; delete the notebook instead.")
        else:
            st.session_state[pending_delete] = True
            st.rerun()
