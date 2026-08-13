"""Moments Jump-to-page page_id resolution."""

from __future__ import annotations

from transcribe.ui.analysis_product_views import _page_id_for_moment


def test_page_id_for_moment_prefers_explicit_page_id():
    assert (
        _page_id_for_moment(
            {"page_id": "p1", "unit_id": "other"},
            evidence_by_unit={},
        )
        == "p1"
    )


def test_page_id_for_moment_from_evidence_source_ref():
    assert (
        _page_id_for_moment(
            {"unit_id": "u1"},
            evidence_by_unit={
                "u1": {"unit_id": "u1", "source_ref": {"kind": "page", "page_id": "p2"}}
            },
        )
        == "p2"
    )


def test_page_id_for_moment_paragraph_unit_id():
    assert (
        _page_id_for_moment(
            {"unit_id": "abc123/span:10-40"},
            evidence_by_unit={},
        )
        == "abc123"
    )


def test_page_id_for_moment_page_v1_unit_id():
    assert (
        _page_id_for_moment({"unit_id": "page-uuid"}, evidence_by_unit={})
        == "page-uuid"
    )
