"""Hardening helpers for Detection wave 2 (review carry-forward)."""

from __future__ import annotations

from transcribe.detection.findings import (
    DetectionFinding,
    carry_forward_reviews,
    derive_review_status,
)


def _finding(
    *,
    finding_id: str,
    start: str,
    end: str,
    finding_type: str = "poetry",
    review_status: str = "unreviewed",
) -> DetectionFinding:
    return DetectionFinding(
        finding_id=finding_id,
        detector_id="poetry",
        detector_version="1",
        notebook_id="nb",
        start_page_id=start,
        end_page_id=end,
        finding_type=finding_type,
        confidence=0.9,
        evidence={"reason": "x", "snippets": []},
        prompt_provenance={"prompt_id": "poetry_detect_text_v1", "version": "1"},
        model_provenance={
            "model_name": "m",
            "model_digest": None,
            "input_mode": "text",
        },
        input_fingerprint="fp",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        review_status=review_status,
    )


def test_carry_forward_preserves_approved_rejected_by_span():
    prior = {
        "findings": [
            _finding(finding_id="old1", start="p1", end="p2", review_status="approved").as_dict(),
            _finding(finding_id="old2", start="p3", end="p3", review_status="rejected").as_dict(),
            _finding(finding_id="old3", start="p9", end="p9", review_status="unreviewed").as_dict(),
        ]
    }
    new = [
        _finding(finding_id="n1", start="p1", end="p2"),
        _finding(finding_id="n2", start="p3", end="p3"),
        _finding(finding_id="n3", start="p4", end="p4"),
    ]
    out = carry_forward_reviews(new, prior)
    by_id = {f.finding_id: f.review_status for f in out}
    assert by_id["n1"] == "approved"
    assert by_id["n2"] == "rejected"
    assert by_id["n3"] == "unreviewed"


def test_carry_forward_noop_without_prior():
    new = [_finding(finding_id="n1", start="p1", end="p1")]
    out = carry_forward_reviews(new, None)
    assert out[0].review_status == "unreviewed"


def test_derive_review_status_partial_span():
    span = ["p1", "p2", "p3", "p4"]
    assert derive_review_status(span, {}) == "unreviewed"
    assert derive_review_status(span, {"p4": "rejected"}) == "unreviewed"
    assert (
        derive_review_status(
            span,
            {"p1": "approved", "p2": "approved", "p3": "approved", "p4": "rejected"},
        )
        == "approved"
    )
    assert derive_review_status(span, {pid: "rejected" for pid in span}) == "rejected"


def test_carry_forward_preserves_page_reviews():
    prior_finding = _finding(finding_id="old1", start="p1", end="p4", review_status="approved")
    prior_finding.page_reviews = {"p1": "approved", "p4": "rejected"}
    prior = {"findings": [prior_finding.as_dict()]}
    new = [_finding(finding_id="n1", start="p1", end="p4")]
    out = carry_forward_reviews(new, prior)
    assert out[0].review_status == "approved"
    assert out[0].page_reviews == {"p1": "approved", "p4": "rejected"}
