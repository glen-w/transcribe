"""Run Detection + Findings panels (Analyse-adjacent)."""

from __future__ import annotations

import streamlit as st

from transcribe.detection.api import DetectionService, DetectorInfo
from transcribe.detection.findings import DetectionFinding
from transcribe.detection.registry import list_all_detectors
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.services.project import ProjectService
from transcribe.ui import icons as ic
from transcribe.ui.detection_tag_review import render_finding_tag_actions
from transcribe.ui.page_viewer import open_page_context
from transcribe.ui.shell import render_page_shell


def render_detection_workspace(
    *,
    projects: ProjectService,
    project_root: str,
    project_id: str = "nb",
    show_shell: bool = True,
) -> None:
    if show_shell:
        render_page_shell(
            "Detect",
            "Scan notebook pages for poetry, lists, to-dos, quotations, beer labels, "
            "first-person I, swear words, and custom phenomena.",
        )

    @st.fragment
    def _detect_body() -> None:
        tabs = st.tabs(["Run Detection", "Findings"])
        with tabs[0]:
            _render_run(projects, project_id=project_id)
        with tabs[1]:
            _render_findings(projects, project_root, project_id=project_id)

    _detect_body()


def _render_run(projects: ProjectService, *, project_id: str) -> None:
    svc = DetectionService(projects)
    dets = list_all_detectors()
    options = {f"{d.title} ({d.detector_id})": d.detector_id for d in dets}
    selected_labels = st.multiselect(
        "Detectors",
        list(options.keys()),
        default=[next(iter(options))] if options else [],
        key=f"detect_run_detectors_{project_id}",
    )
    project = projects.load()
    page_labels = {
        f"Page {i + 1} ({p.page_id[:8]}…)": p.page_id for i, p in enumerate(project.pages)
    }
    scope = st.radio(
        "Scope",
        ["Whole notebook", "Selected pages"],
        horizontal=True,
        key=f"detect_scope_{project_id}",
    )
    page_ids = None
    if scope == "Selected pages":
        chosen = st.multiselect(
            "Pages",
            list(page_labels.keys()),
            key=f"detect_pages_{project_id}",
        )
        page_ids = [page_labels[c] for c in chosen]

    force = st.checkbox(
        "Force rerun (ignore cache)",
        value=False,
        key=f"detect_force_{project_id}",
    )
    from transcribe.services.tags import TagService

    tag_svc = TagService()
    auto_key = f"detect_auto_tag_{project_id}"
    if auto_key not in st.session_state:
        st.session_state[auto_key] = bool(
            selected_labels
            and any(tag_svc.auto_tag_enabled(options[label]) for label in selected_labels)
        )
    auto_tag = st.checkbox(
        "Tag matching pages",
        key=auto_key,
        help="Add each detector’s tag to pages in published findings (additive). "
        "Does not change detection cache identity. Re-running re-adds tags you removed.",
    )
    progress = st.empty()
    status = st.empty()

    if st.button("Run detection", type="primary", width="stretch", key=f"detect_run_{project_id}", icon=ic.SEARCH_CHECK):
        if not selected_labels:
            st.warning("Select at least one detector.")
            return
        for label in selected_labels:
            did = options[label]
            status.info(f"Running `{did}`…")

            def _progress(done: int, total: int, _did: str = did) -> None:
                progress.progress(
                    min(1.0, done / max(1, total)),
                    text=f"{_did}: {done}/{total} windows",
                )

            try:
                result = svc.run_detector(
                    did,
                    page_ids=page_ids,
                    force=force,
                    progress_callback=_progress,
                    auto_tag=auto_tag,
                )
                n = len(result.get("findings") or [])
                outcome = result.get("outcome")
                tagged = result.get("auto_tagged_pages")
                extra = f", tagged {tagged} page(s)" if auto_tag and tagged is not None else ""
                status.success(f"`{did}` → {outcome}, {n} finding(s){extra}")
                if result.get("warnings"):
                    with st.expander(f"Warnings ({did})"):
                        st.json(result["warnings"])
            except Exception as exc:  # noqa: BLE001
                status.error(f"`{did}` failed: {exc}")

    st.divider()
    st.markdown("#### Freshness")
    for d in dets:
        fresh = svc.freshness(d.detector_id)
        attempt_state = svc.latest_attempt_state(d.detector_id)
        note = ""
        if attempt_state in ("interrupted", "cancelled", "failed", "running"):
            note = f" · last attempt: **{attempt_state}**"
        st.caption(f"`{d.detector_id}`: **{fresh}**{note}")


def _page_label(page_id: str, page_order: dict[str, int]) -> str:
    idx = page_order.get(page_id)
    if isinstance(idx, int):
        return f"Page {idx + 1}"
    return f"Page {page_id[:8]}…"


def _render_page_scan_and_text(
    projects: ProjectService,
    project,
    page_id: str,
    *,
    label: str,
    key_prefix: str,
) -> None:
    page = next((p for p in project.pages if p.page_id == page_id), None)
    if page is None:
        st.caption(f"{label} — page not found")
        return
    render = project.renders.get(page.active_render_id)
    if render is None:
        st.caption(f"{label} — no scan")
        return
    img_path = projects.paths.resolve_contained(render.image_relpath)
    result = projects.load_page_result(page_id)
    ocr_text = (result.effective_text() if result else None) or ""
    img_col, text_col = st.columns([1, 1])
    with img_col:
        st.caption(label)
        if img_path.is_file():
            st.image(str(img_path), width="stretch")
        else:
            st.caption("Scan image unavailable")
    with text_col:
        st.caption("OCR text")
        if ocr_text.strip():
            st.text_area(
                "OCR text",
                value=ocr_text,
                height=360,
                disabled=True,
                key=f"{key_prefix}_ocr_{page_id}",
                label_visibility="collapsed",
            )
        else:
            st.caption("No OCR text yet — run Transcribe first.")


def _render_finding_page_context(
    projects: ProjectService,
    project,
    page_ids: list[str],
    *,
    page_order: dict[str, int],
    key_prefix: str,
) -> None:
    if not page_ids:
        return
    st.markdown(
        """
<style>
div[data-testid="stExpanderDetails"] div[data-testid="stImage"] img {
    max-height: 45vh;
    width: auto;
    max-width: 100%;
    object-fit: contain;
}
</style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("**Page context**")
    if len(page_ids) == 1:
        _render_page_scan_and_text(
            projects,
            project,
            page_ids[0],
            label=_page_label(page_ids[0], page_order),
            key_prefix=key_prefix,
        )
        return
    tabs = st.tabs([_page_label(pid, page_order) for pid in page_ids])
    for tab, page_id in zip(tabs, page_ids):
        with tab:
            _render_page_scan_and_text(
                projects,
                project,
                page_id,
                label=_page_label(page_id, page_order),
                key_prefix=f"{key_prefix}_{page_id}",
            )


@st.fragment
def _render_findings(projects: ProjectService, project_root: str, *, project_id: str) -> None:
    """One detector type at a time — Streamlit tabs still render every pane."""
    svc = DetectionService(projects)
    infos = svc.list_detectors()
    if not infos:
        st.caption("No detectors registered.")
        return

    type_ids = [info.detector_id for info in infos]
    titles = {info.detector_id: info.title for info in infos}
    key = f"detect_findings_type_{project_id}"
    if st.session_state.get(key) not in type_ids:
        st.session_state[key] = _default_finding_type(svc, infos)
    selected_id = st.segmented_control(
        "Finding type",
        options=type_ids,
        format_func=lambda did: titles[did],
        key=key,
        label_visibility="collapsed",
        required=True,
        width="stretch",
    )
    if selected_id is None or selected_id not in titles:
        selected_id = st.session_state.get(key) or type_ids[0]
    info = next(item for item in infos if item.detector_id == selected_id)
    _render_finding_type(
        svc,
        info,
        svc.list_findings(info.detector_id),
        projects=projects,
        project_root=project_root,
        project_id=project_id,
    )


def _default_finding_type(svc: DetectionService, infos: list[DetectorInfo]) -> str:
    for info in infos:
        if svc.storage.published_path(info.detector_id).exists():
            return info.detector_id
    return infos[0].detector_id


def _render_finding_type(
    svc: DetectionService,
    info: DetectorInfo,
    findings: list[DetectionFinding],
    *,
    projects: ProjectService,
    project_root: str,
    project_id: str,
) -> None:
    project = projects.load()
    page_order = {p.page_id: i for i, p in enumerate(project.pages)}
    fresh = svc.freshness(info.detector_id)
    if not findings:
        st.caption(
            f"{info.title} `{info.detector_id}` · freshness: **{fresh}** — "
            "no published findings yet."
        )
        return
    head = st.columns([5, 2])
    head[0].markdown(f"### {info.title} `{info.detector_id}` · freshness: **{fresh}**")
    if head[1].button(
        "Apply tags from findings",
        key=f"apply_tags_{project_id}_{info.detector_id}",
        help="Tag pages in published findings without re-running detection.",
    ):
        n = svc.apply_tags_from_published(info.detector_id)
        st.success(f"Tagged {n} page(s)")
        st.rerun()
    for f in findings:
        start_i = page_order.get(f.start_page_id, "?")
        end_i = page_order.get(f.end_page_id, "?")
        span = (
            f"pages {start_i + 1}–{end_i + 1}"
            if isinstance(start_i, int) and isinstance(end_i, int)
            else f"{f.start_page_id}…{f.end_page_id}"
        )
        with st.expander(f"{f.finding_type} · {span} · {f.confidence:.0%} · {f.review_status}"):
            st.write(escape_markdown_plain(str(f.evidence.get("reason") or "")))
            span_page_ids = svc._page_ids_between(f.start_page_id, f.end_page_id)
            _render_finding_page_context(
                projects,
                project,
                span_page_ids,
                page_order=page_order,
                key_prefix=f"find_{project_id}_{f.finding_id}",
            )
            if f.detector_data:
                with st.expander("Detector details"):
                    st.json(f.detector_data)
            st.caption(
                f"prompt={f.prompt_provenance} model={f.model_provenance.get('model_name')}"
            )
            render_finding_tag_actions(
                det_svc=svc,
                detector_id=info.detector_id,
                finding=f,
                key_prefix=f"find_{project_id}",
            )
            c1, c2 = st.columns(2)
            if c1.button("Open pages", key=f"open_{project_id}_{f.finding_id}"):
                ids = svc._page_ids_between(f.start_page_id, f.end_page_id)
                open_page_context(
                    page_id=f.start_page_id,
                    page_ids=ids,
                    project_root=project_root,
                    return_mode="Detect",
                    view_entries=[
                        {"page_id": pid, "project_root": project_root} for pid in ids
                    ],
                )
                st.session_state["ui_mode"] = "Detect"
                st.rerun()
            if c2.button("Rerun detector", key=f"rr_{project_id}_{f.finding_id}"):
                svc.run_detector(info.detector_id, force=True)
                st.rerun()
