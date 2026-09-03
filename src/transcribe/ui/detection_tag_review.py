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


def _accept_finding(det_svc: DetectionService, finding: DetectionFinding) -> None:
    try:
        n = det_svc.accept_finding(finding)
        bump_archive_generation(build_runtime_paths())
        if n:
            tag_label = finding_tag_label(det_svc, finding)
            st.toast(f"Accepted — tagged {n} page{'s' if n != 1 else ''} with `{tag_label}`")
        st.rerun()
    except TranscribeError as exc:
        st.error(str(exc))


def _reject_finding(det_svc: DetectionService, finding: DetectionFinding) -> None:
    try:
        det_svc.reject_finding(finding)
        bump_archive_generation(build_runtime_paths())
        st.rerun()
    except TranscribeError as exc:
        st.error(str(exc))


def _set_page_review(
    det_svc: DetectionService,
    finding: DetectionFinding,
    page_id: str,
    status: str,
) -> None:
    if status not in ("approved", "rejected"):
        return
    try:
        det_svc.set_page_review(finding, page_id, status)
        bump_archive_generation(build_runtime_paths())
        st.rerun()
    except TranscribeError as exc:
        st.error(str(exc))


def finding_tag_label(det_svc: DetectionService, finding: DetectionFinding) -> str:
    slug = det_svc.finding_tag_slug(
        finding.detector_id,
        finding_type=finding.finding_type,
        finding=finding,
    )
    try:
        catalog = TagService().load_catalog()
        return display_tag(catalog, slug).label
    except Exception:  # noqa: BLE001
        return det_svc.finding_tag_label(finding.detector_id, slug=slug, finding=finding)


def render_span_page_review(
    *,
    det_svc: DetectionService,
    finding: DetectionFinding,
    page_id: str,
    key_prefix: str,
) -> None:
    """Accept / Reject this page inside a multi-page finding."""
    status = finding.page_reviews.get(page_id, "unreviewed")
    tag_label = finding_tag_label(det_svc, finding)
    if status == "approved":
        st.caption(f"Accepted on this page — tag `{tag_label}` stays.")
    elif status == "rejected":
        st.caption(f"Rejected on this page — tag `{tag_label}` removed.")
    else:
        st.caption("This page in the finding — accept or reject independently.")
    c1, c2 = st.columns(2)
    if c1.button(
        "Accept this page",
        key=f"{key_prefix}_ac_pg_{page_id}",
        help=f"Keep this page in the finding and apply tag `{tag_label}`",
        icon=ic.CHECK_CIRCLE,
        type="primary" if status != "approved" else "secondary",
        disabled=status == "approved",
    ):
        _set_page_review(det_svc, finding, page_id, "approved")
    if c2.button(
        "Reject this page",
        key=f"{key_prefix}_rj_pg_{page_id}",
        help="Exclude this page from the finding and remove its tag",
        icon=ic.REJECT,
        disabled=status == "rejected",
    ):
        _set_page_review(det_svc, finding, page_id, "rejected")


def render_page_detection_tag_row(
    *,
    det_svc: DetectionService,
    finding: DetectionFinding,
    page_id: str,
    key_prefix: str,
) -> None:
    """One detection row with Accept / ✓ / ✓✓ / ✕ (dates-style)."""
    fresh = det_svc.freshness(finding.detector_id)
    stale = "" if fresh == "ok" else f" · {fresh}"
    slug = det_svc.finding_tag_slug(
        finding.detector_id,
        finding_type=finding.finding_type,
        finding=finding,
    )
    span_ids = det_svc.span_page_ids(finding)
    missing_here = page_id in det_svc.pages_missing_tag([page_id], slug)
    missing_span = det_svc.pages_missing_tag(span_ids, slug)
    tag_label = finding_tag_label(det_svc, finding)
    page_status = finding.page_reviews.get(page_id, "unreviewed")
    rejected = finding.review_status == "rejected" or page_status == "rejected"
    multi_page = len(span_ids) > 1
    show_tag_actions = not rejected and bool(missing_here or missing_span)

    if page_status == "rejected":
        status_note = f"Rejected on this page — tag `{tag_label}` removed"
    elif show_tag_actions and missing_here:
        status_note = f"Proposed tag `{tag_label}` — not yet on this page"
    elif show_tag_actions:
        status_note = f"Proposed tag `{tag_label}` — on this page, pending on others"
    else:
        status_note = None

    actions: list[str] = []
    if page_status != "approved":
        actions.append("accept")
    if show_tag_actions and missing_here:
        actions.append("tag")
    if show_tag_actions and missing_span and multi_page:
        actions.append("tag_all")
    if page_status != "rejected":
        actions.append("reject")

    weights = [max(4, 10 - len(actions))] + [1] * len(actions)
    cols = st.columns(weights)
    summary = (
        f"{finding.finding_type} · {finding.confidence:.0%} · {finding.review_status}{stale}"
    )
    if status_note:
        summary = f"{summary} · {status_note}"
    cols[0].write(summary)

    for i, action in enumerate(actions, start=1):
        col = cols[i]
        if action == "accept":
            help_text = (
                "Accept this page"
                if multi_page
                else "Accept detection"
            )
            if col.button(
                "",
                key=f"{key_prefix}_ac_{finding.finding_id}_{page_id}",
                help=help_text,
                type="tertiary",
                icon=ic.CHECK_CIRCLE,
            ):
                if multi_page:
                    _set_page_review(det_svc, finding, page_id, "approved")
                else:
                    _accept_finding(det_svc, finding)
                return
        elif action == "tag":
            if col.button(
                "",
                key=f"{key_prefix}_tag_{finding.finding_id}",
                help=f"Apply tag `{tag_label}` to this page",
                type="tertiary",
                icon=ic.CHECK,
            ):
                try:
                    det_svc.apply_finding_tag(
                        finding, [page_id], approve_finding=len(span_ids) == 1
                    )
                    bump_archive_generation(build_runtime_paths())
                    st.rerun()
                except TranscribeError as exc:
                    st.error(str(exc))
        elif action == "tag_all":
            if col.button(
                "",
                key=f"{key_prefix}_tag_all_{finding.finding_id}",
                help=(
                    f"Apply tag `{tag_label}` to remaining pages in this finding"
                ),
                type="tertiary",
                icon=ic.CHECK_ALL,
            ):
                _accept_finding(det_svc, finding)
                return
        elif action == "reject":
            help_text = (
                "Reject this page (keep other pages in the finding)"
                if multi_page
                else "Reject detection"
            )
            if col.button(
                "",
                key=f"{key_prefix}_rj_{finding.finding_id}_{page_id}",
                help=help_text,
                type="tertiary",
                icon=ic.CLOSE,
            ):
                if multi_page:
                    _set_page_review(det_svc, finding, page_id, "rejected")
                else:
                    _reject_finding(det_svc, finding)


def render_finding_tag_actions(
    *,
    det_svc: DetectionService,
    detector_id: str,
    finding: DetectionFinding,
    key_prefix: str,
) -> None:
    """Accept remaining / Reject all for the Detect → Findings expander."""
    slug = det_svc.finding_tag_slug(
        detector_id,
        finding_type=finding.finding_type,
        finding=finding,
    )
    span_ids = det_svc.span_page_ids(finding)
    missing_span = det_svc.pages_missing_tag(span_ids, slug)
    tag_label = finding_tag_label(det_svc, finding)
    rejected = finding.review_status == "rejected"
    approved = finding.review_status == "approved"
    rejected_pages = [
        pid for pid in span_ids if finding.page_reviews.get(pid) == "rejected"
    ]
    accepted_pages = [
        pid for pid in span_ids if finding.page_reviews.get(pid) == "approved"
    ]

    if rejected:
        st.caption("Rejected — tag will not be applied.")
        if st.button(
            "Accept",
            key=f"{key_prefix}_ac_{finding.finding_id}",
            help="Accept detection and apply remaining tags",
            icon=ic.CHECK_CIRCLE,
        ):
            _accept_finding(det_svc, finding)
        return

    parts: list[str] = []
    if not missing_span and not rejected_pages:
        parts.append(f"Tag `{tag_label}` is on all pages in this finding.")
    elif missing_span:
        parts.append(
            f"Proposed tag `{tag_label}` — pending on {len(missing_span)} of "
            f"{len(span_ids)} page(s)."
        )
    if rejected_pages:
        parts.append(
            f"Rejected {len(rejected_pages)} of {len(span_ids)} page(s). "
            "Accept remaining keeps the others."
        )
    elif len(span_ids) > 1:
        parts.append("Use Accept / Reject this page on each tab to split the span.")
    if parts:
        st.caption(" ".join(parts))

    if approved:
        if st.button(
            "Reject all",
            key=f"{key_prefix}_rj_{finding.finding_id}",
            help="Reject detection on every page",
            icon=ic.REJECT,
        ):
            _reject_finding(det_svc, finding)
        return

    accept_label = "Accept remaining" if rejected_pages or accepted_pages else "Accept"
    c1, c2 = st.columns(2)
    if c1.button(
        accept_label,
        key=f"{key_prefix}_ac_{finding.finding_id}",
        help=f"Accept remaining pages and apply tag `{tag_label}` (skips rejected pages)",
        icon=ic.CHECK_CIRCLE,
        type="primary",
    ):
        _accept_finding(det_svc, finding)
    if c2.button(
        "Reject all",
        key=f"{key_prefix}_rj_{finding.finding_id}",
        help="Reject detection on every page (remove tags)",
        icon=ic.REJECT,
    ):
        _reject_finding(det_svc, finding)
