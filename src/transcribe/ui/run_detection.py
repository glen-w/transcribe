"""Run Detection + Findings panels (Analyse-adjacent)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcribe.detection.api import DetectionService
from transcribe.detection.registry import list_all_detectors
from transcribe.services.project import ProjectService
from transcribe.ui.page_viewer import open_page_context
from transcribe.ui.shell import render_page_shell


def render_detection_workspace(
    *,
    projects: ProjectService,
    project_root: str,
) -> None:
    render_page_shell(
        "Detect",
        "Scan notebook pages for poetry, lists, to-dos, quotations, and custom phenomena.",
    )
    tabs = st.tabs(["Run Detection", "Findings"])
    with tabs[0]:
        _render_run(projects)
    with tabs[1]:
        _render_findings(projects, project_root)


def _render_run(projects: ProjectService) -> None:
    svc = DetectionService(projects)
    dets = list_all_detectors()
    options = {f"{d.title} ({d.detector_id})": d.detector_id for d in dets}
    selected_labels = st.multiselect(
        "Detectors",
        list(options.keys()),
        default=[next(iter(options))] if options else [],
        key="detect_run_detectors",
    )
    project = projects.load()
    page_labels = {
        f"Page {i + 1} ({p.page_id[:8]}…)": p.page_id
        for i, p in enumerate(project.pages)
    }
    scope = st.radio("Scope", ["Whole notebook", "Selected pages"], horizontal=True)
    page_ids = None
    if scope == "Selected pages":
        chosen = st.multiselect("Pages", list(page_labels.keys()))
        page_ids = [page_labels[c] for c in chosen]

    force = st.checkbox("Force rerun (ignore cache)", value=False)
    progress = st.empty()
    status = st.empty()

    if st.button("Run detection", type="primary", use_container_width=True):
        if not selected_labels:
            st.warning("Select at least one detector.")
            return
        for label in selected_labels:
            did = options[label]
            status.info(f"Running `{did}`…")

            def _progress(done: int, total: int, _did: str = did) -> None:
                progress.progress(min(1.0, done / max(1, total)), text=f"{_did}: {done}/{total} windows")

            try:
                result = svc.run_detector(
                    did,
                    page_ids=page_ids,
                    force=force,
                    progress_callback=_progress,
                )
                n = len(result.get("findings") or [])
                outcome = result.get("outcome")
                status.success(f"`{did}` → {outcome}, {n} finding(s)")
                if result.get("warnings"):
                    with st.expander(f"Warnings ({did})"):
                        st.json(result["warnings"])
            except Exception as exc:  # noqa: BLE001
                status.error(f"`{did}` failed: {exc}")

    st.divider()
    st.markdown("#### Freshness")
    for d in dets:
        fresh = svc.freshness(d.detector_id)
        st.caption(f"`{d.detector_id}`: **{fresh}**")


def _render_findings(projects: ProjectService, project_root: str) -> None:
    svc = DetectionService(projects)
    project = projects.load()
    page_order = {p.page_id: i for i, p in enumerate(project.pages)}

    for info in svc.list_detectors():
        findings = svc.list_findings(info.detector_id)
        if not findings:
            continue
        fresh = svc.freshness(info.detector_id)
        st.markdown(f"### {info.title} `{info.detector_id}` · freshness: **{fresh}**")
        for f in findings:
            start_i = page_order.get(f.start_page_id, "?")
            end_i = page_order.get(f.end_page_id, "?")
            span = (
                f"pages {start_i + 1}–{end_i + 1}"
                if isinstance(start_i, int) and isinstance(end_i, int)
                else f"{f.start_page_id}…{f.end_page_id}"
            )
            with st.expander(
                f"{f.finding_type} · {span} · {f.confidence:.0%} · {f.review_status}"
            ):
                st.write(f.evidence.get("reason") or "")
                if f.detector_data:
                    st.json(f.detector_data)
                st.caption(
                    f"prompt={f.prompt_provenance} model={f.model_provenance.get('model_name')}"
                )
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("Open pages", key=f"open_{f.finding_id}"):
                    ids = svc._page_ids_between(f.start_page_id, f.end_page_id)
                    open_page_context(
                        page_id=f.start_page_id,
                        page_ids=ids,
                        project_root=project_root,
                        return_mode="Analyse",
                        view_entries=[
                            {"page_id": pid, "project_root": project_root} for pid in ids
                        ],
                    )
                    st.rerun()
                if c2.button("Approve", key=f"ap_{f.finding_id}"):
                    svc.set_review_status(info.detector_id, f.finding_id, "approved")
                    st.rerun()
                if c3.button("Reject", key=f"rj_{f.finding_id}"):
                    svc.set_review_status(info.detector_id, f.finding_id, "rejected")
                    st.rerun()
                if c4.button("Rerun detector", key=f"rr_{f.finding_id}"):
                    svc.run_detector(info.detector_id, force=True)
                    st.rerun()
