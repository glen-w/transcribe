"""Source-contract checks for Import/Transcribe Target switchers (no Streamlit runtime)."""

from __future__ import annotations

from pathlib import Path

from transcribe.persistence.schema import SUPPORTED


APP = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
SHELL = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
IMPORT = Path("src/transcribe/ui/run_import.py").read_text(encoding="utf-8")
TRANSCRIBE = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
INBOX = Path("src/transcribe/ui/import_inbox.py").read_text(encoding="utf-8")


def test_inbox_is_not_a_sidebar_mode() -> None:
    assert '_NOTEBOOK_MODES: tuple[str, ...] = ("View", "Search", "Archive", "Places")' in SHELL
    assert '"Inbox": "Import"' in SHELL
    assert 'elif mode == "Inbox"' not in APP
    assert "render_run_import" in APP
    assert "render_run_transcribe" in APP


def test_import_and_transcribe_use_target_switcher() -> None:
    assert 'st.segmented_control' in IMPORT
    assert 'st.segmented_control' in TRANSCRIBE
    assert "This notebook" in IMPORT and "Batch" in IMPORT
    assert "This notebook" in TRANSCRIBE and "Batch" in TRANSCRIBE
    assert "Start batch transcription" in TRANSCRIBE
    assert "queue_transcribe_imported" in INBOX
    assert "Transcribe imported notebooks" in INBOX


def test_ocr_batch_run_format_registered() -> None:
    assert SUPPORTED.get("transcribe.ocr-batch-run") == 1
    contract = Path("docs/contracts/ocr-batch-run.md").read_text(encoding="utf-8")
    assert "transcribe.ocr-batch-run" in contract
    assert "JobCoordinator" in contract
