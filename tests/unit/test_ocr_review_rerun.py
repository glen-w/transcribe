"""Review workbench re-run OCR dialog contract (source-level)."""

from pathlib import Path

REVIEW = Path("src/transcribe/ui/review_workbench.py").read_text(encoding="utf-8")


def test_review_rerun_ocr_opens_model_and_scope_dialog() -> None:
    assert '@st.dialog("Re-run OCR")' in REVIEW
    assert '"Re-run OCR"' in REVIEW
    assert "Vision model" in REVIEW
    assert "render_model_information" in REVIEW
    assert '"This page"' in REVIEW
    assert "All pages (" in REVIEW
    assert "All pages not marked as reviewed" in REVIEW
    assert "get_coordinator" in REVIEW
    assert "model_name=chosen" in REVIEW
    assert 'scope="not_reviewed"' in REVIEW
    assert "Re-run OCR on this page" not in REVIEW
    assert "Build merged draft" in REVIEW or "Rank and merge" in REVIEW
    assert "start_compare_existing" in REVIEW


def test_review_tabs_split_ocr_and_cleanup() -> None:
    assert "_LANE_OCR" in REVIEW
    assert "_LANE_CLEANUP" in REVIEW
    assert "def _render_ocr_tab(" in REVIEW
    assert "def _render_cleanup_tab(" in REVIEW
    assert "All pages in notebook (" in REVIEW
    assert "reapply_visual_declutter(" in REVIEW
    assert "_render_ocr_settings(projects, project, page.page_id)" in REVIEW
    assert (
        "_render_ocr_settings(projects, project, page.page_id)"
        not in REVIEW.split("def _render_other_tab")[-1]
    )
    assert "st.tabs(" not in REVIEW
