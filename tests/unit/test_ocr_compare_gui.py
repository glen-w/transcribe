"""Review workbench OCR compare GUI contracts (source-level)."""

from pathlib import Path

REVIEW = Path("src/transcribe/ui/review_workbench.py").read_text(encoding="utf-8")
PAGE = Path("src/transcribe/ui/page_viewer.py").read_text(encoding="utf-8")
TRANSCRIBE = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
APP = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
QUEUE = Path("src/transcribe/ui/review_queue.py").read_text(encoding="utf-8")


def test_review_lane_switcher_not_st_tabs() -> None:
    assert "st.tabs(" not in REVIEW
    assert "st.segmented_control(" in REVIEW
    assert '"Review lane"' in REVIEW
    assert "_render_transcription_lane(" in REVIEW
    assert "_render_ocr_comparison_band(" in REVIEW
    # Comparison band is invoked from Transcription lane, not after both panes.
    trans_idx = REVIEW.index("def _render_transcription_lane(")
    band_call = REVIEW.index("_render_ocr_comparison_band(", trans_idx)
    band_def = REVIEW.index("def _render_ocr_comparison_band(")
    assert band_call < band_def


def test_review_lane_persists_across_pages() -> None:
    assert '_LANE_SESSION_KEY = "rw_lane"' in REVIEW
    assert "lane_key = _LANE_SESSION_KEY" in REVIEW
    assert 'key=f"rw_lane_{page_id}"' not in REVIEW


def test_review_icon_disagreement_nav() -> None:
    assert "_PREV_DISAGREEMENT_HELP" in REVIEW
    assert "_NEXT_DISAGREEMENT_HELP" in REVIEW
    assert 'help=_PREV_DISAGREEMENT_HELP' in REVIEW
    assert 'help=_NEXT_DISAGREEMENT_HELP' in REVIEW
    assert '"Previous disagreement"' not in REVIEW.split("def _render_disagreement_panel")[1].split(
        "def _apply_region_choice"
    )[0]


def test_review_build_merged_draft_and_confirm_all() -> None:
    assert '"Build merged draft"' in REVIEW
    assert "Confirm rank and merge all" in REVIEW
    assert "rw_comparable_page_ids" in REVIEW
    assert "build_review_queue_index" in APP
    assert "default_review_filter" in APP


def test_page_viewer_compare_in_review_not_prefer_promote() -> None:
    assert "_render_compare_in_review(" in PAGE
    assert '"Compare in Review"' in PAGE
    assert "jump_to_review" in PAGE
    assert "_render_attempt_compare" not in PAGE
    assert 'button("Prefer"' not in PAGE
    assert 'button("Promote"' not in PAGE
    assert 'expander("Compare OCR attempts"' not in PAGE
    assert "_COMPARE_SCAN_IMAGE_WIDTH_PX" not in PAGE
    # Reading (read_only) must deep-link too — not only Archive edit mode.
    call_idx = PAGE.index("_render_compare_in_review(")
    guard = PAGE[max(0, call_idx - 80) : call_idx]
    assert "if not read_only:" not in guard


def test_transcribe_seed_checkbox_polarity() -> None:
    assert "Seed transcription from merged draft after multipass" in TRANSCRIBE
    assert "Do not auto-activate composite" not in TRANSCRIBE
    assert "When setting a notebook default" in TRANSCRIBE
    assert "Prefer = promote" not in TRANSCRIBE
    assert "Auto-activate composite after multipass" not in TRANSCRIBE


def test_review_edit_gate_and_failed_attempt_caption_contracts() -> None:
    assert "prefer_promote_with_edit_gate" in REVIEW
    assert "Confirm Use as current text" in REVIEW
    assert "Failed:" in REVIEW
    assert "rationale_by_id" in REVIEW
    assert "Rank:" in REVIEW


def test_review_queue_ignores_stale_cached_disagreement_count() -> None:
    """Queue helper must re-align; do not trust persisted source_disagreement_count."""
    assert "reviewable spans only" in QUEUE
    fn = QUEUE.split("def source_disagreement_count(")[1].split("\ndef ")[0]
    assert "result.source_disagreement_count is not None" not in fn
    assert "align_ocr(" in fn


def test_review_queue_single_pass_helpers() -> None:
    assert "class ReviewQueueIndex" in QUEUE
    assert "def build_review_queue_index(" in QUEUE
    assert "def default_review_filter(" in QUEUE
    assert "comparable_page_ids" in QUEUE
