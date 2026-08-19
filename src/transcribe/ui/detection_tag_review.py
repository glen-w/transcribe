"""Shared detection tag approval controls (page viewer + Detect findings)."""

from __future__ import annotations

import streamlit as st

from transcribe.detection.api import DetectionService
from transcribe.detection.findings import DetectionFinding
from transcribe.errors import TranscribeError
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import bump_archive_generation
from transcribe.services.tags import TagService
from transcribe.ui import icons as ic
from transcribe.tagging.kernel import display_tag


def finding_tag_label(det_svc: DetectionService, finding: DetectionFinding) -> str:
    slug = det_svc.finding_tag_slug(finding.detector_id, finding_type=finding.finding_type)
    try:
        catalog = TagService().load_catalog()
        return display_tag(catalog, slug).label
    except Exception:  # noqa: BLE001
        return det_svc.finding_tag_label(finding.detector_id, slug=slug)


def render_page_detection_tag_row(
    *,
    det_svc: DetectionService,
    finding: DetectionFinding,
    page_id: str,
    key_prefix: str,
) -> None:
    """One detection row with ✓ / ✓✓ / ✕ tag approval (dates-style)."""
    fresh = det_svc.freshness(finding.detector_id)
    stale = "" if fresh == "ok" else f" · {fresh}"
    slug = det_svc.finding_tag_slug(finding.detector_id, finding_type=finding.finding_type)
    span_ids = det_svc.span_page_ids(finding)
    missing_here = page_id in det_svc.pages_missing_tag([page_id], slug)
    missing_span = det_svc.pages_missing_tag(span_ids, slug)
    tag_label = finding_tag_label(det_svc, finding)
    rejected = finding.review_status == "rejected"
    show_actions = not rejected and bool(missing_here or missing_span)

    if show_actions and missing_here:
        status_note = f"Proposed tag `{tag_label}` — not yet on this page"
    elif show_actions:
        status_note = f"Proposed tag `{tag_label}` — on this page, pending on others"
    else:
        status_note = None

    cols = st.columns([6, 1, 1, 1] if show_actions else [8, 1, 1])
    summary = (
        f"{finding.finding_type} · {finding.confidence:.0%} · {finding.review_status}{stale}"
    )
    if status_note:
        summary = f"{summary} · {status_note}"
    cols[0].write(summary)

    if not show_actions:
        if not rejected and cols[1].button(
            "",
            key=f"{key_prefix}_rj_{finding.finding_id}",
            help="Reject detection",
            type="tertiary",
            icon=ic.CLOSE,
        ):
            det_svc.set_review_status(finding.detector_id, finding.finding_id, "rejected")
            st.rerun()
        return

    if missing_here and cols[1].button(
        "",
        key=f"{key_prefix}_tag_{finding.finding_id}",
        help=f"Apply tag `{tag_label}` to this page",
        type="tertiary",
        icon=ic.CHECK,
    ):
        try:
            det_svc.apply_finding_tag(finding, [page_id], approve_finding=len(span_ids) == 1)
            bump_archive_generation(build_runtime_paths())
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))

    multi_page = len(span_ids) > 1
    if missing_span and multi_page and cols[2].button(
        "",
        key=f"{key_prefix}_tag_all_{finding.finding_id}",
        help=f"Apply tag `{tag_label}` to all {len(missing_span)} page(s) in this finding",
        type="tertiary",
        icon=ic.CHECK_ALL,
    ):
        try:
            n = det_svc.apply_finding_tag(finding, span_ids, approve_finding=True)
            bump_archive_generation(build_runtime_paths())
            if n:
                st.toast(
                    f"Tagged {n} page{'s' if n != 1 else ''} with `{tag_label}`"
                )
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))

    reject_col = cols[3] if show_actions else cols[2]
    if reject_col.button(
        "",
        key=f"{key_prefix}_rj_{finding.finding_id}",
        help="Reject detection (do not apply tag)",
        type="tertiary",
        icon=ic.CLOSE,
    ):
        det_svc.set_review_status(finding.detector_id, finding.finding_id, "rejected")
        st.rerun()


def render_finding_tag_actions(
    *,
    det_svc: DetectionService,
    detector_id: str,
    finding: DetectionFinding,
    key_prefix: str,
) -> None:
    """Tag approval row for the Detect → Findings expander."""
    slug = det_svc.finding_tag_slug(detector_id, finding_type=finding.finding_type)
    span_ids = det_svc.span_page_ids(finding)
    missing_span = det_svc.pages_missing_tag(span_ids, slug)
    tag_label = finding_tag_label(det_svc, finding)
    rejected = finding.review_status == "rejected"

    if rejected:
        st.caption("Rejected — tag will not be applied.")
        return
    if not missing_span:
        st.caption(f"Tag `{tag_label}` is on all pages in this finding.")
        if st.button(
            "Reject",
            key=f"{key_prefix}_rj_{finding.finding_id}",
            help="Reject detection",
            icon=ic.REJECT,
        ):
            det_svc.set_review_status(detector_id, finding.finding_id, "rejected")
            st.rerun()
        return

    st.caption(
        f"Proposed tag `{tag_label}` — pending on {len(missing_span)} of "
        f"{len(span_ids)} page(s). Use page viewer for single-page approval."
    )
    c1, c2 = st.columns(2)
    if c1.button(
        "Tag all pages",
        key=f"{key_prefix}_tag_all_{finding.finding_id}",
        help=f"Apply tag `{tag_label}` to every page in this finding",
        icon=ic.CHECK_ALL,
    ):
        try:
            n = det_svc.apply_finding_tag(finding, span_ids, approve_finding=True)
            bump_archive_generation(build_runtime_paths())
            if n:
                st.success(f"Tagged {n} page(s) with `{tag_label}`")
            st.rerun()
        except TranscribeError as exc:
            st.error(str(exc))
    if c2.button(
        "Reject",
        key=f"{key_prefix}_rj_{finding.finding_id}",
        help="Reject detection (do not apply tag)",
        icon=ic.REJECT,
    ):
        det_svc.set_review_status(detector_id, finding.finding_id, "rejected")
        st.rerun()
