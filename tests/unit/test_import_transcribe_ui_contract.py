"""Source-contract checks for Import/Transcribe Target switchers (no Streamlit runtime)."""

from __future__ import annotations

from pathlib import Path

from transcribe.persistence.schema import SUPPORTED

APP = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
NAV = Path("src/transcribe/ui/navigation.py").read_text(encoding="utf-8")
SHELL = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
IMPORT = Path("src/transcribe/ui/run_import.py").read_text(encoding="utf-8")
TRANSCRIBE = Path("src/transcribe/ui/run_transcribe.py").read_text(encoding="utf-8")
INBOX = Path("src/transcribe/ui/import_inbox.py").read_text(encoding="utf-8")


def test_inbox_is_not_a_sidebar_mode() -> None:
    assert 'PRIMARY_MODES: tuple[str, ...] = tuple(s.id for s in PAGE_SPECS if s.section == "primary")' in NAV
    assert '"Library"' in NAV and '"Search"' in NAV and '"Archive"' in NAV and '"Places"' in NAV
    assert '"Inbox": "Import"' in NAV
    assert 'elif mode == "Inbox"' not in APP
    assert "render_run_import" in APP
    assert "render_run_transcribe" in APP
    assert "_NOTEBOOK_MODES" not in SHELL



def test_import_and_transcribe_use_target_switcher() -> None:
    assert "st.segmented_control" in IMPORT
    assert "st.segmented_control" in TRANSCRIBE
    assert "This notebook" in IMPORT and "Batch" in IMPORT
    assert "This notebook" in TRANSCRIBE and "Batch" in TRANSCRIBE
    assert "Start batch transcription" in TRANSCRIBE
    assert "Start batch multipass compare" in TRANSCRIBE
    assert "tx_batch_start_multipass" in TRANSCRIBE
    assert "_multipass_default_selection" in TRANSCRIBE
    assert 'unit_label="notebooks"' in TRANSCRIBE
    assert "pages in this notebook" in TRANSCRIBE
    assert "_job_progress_to_snapshot" in TRANSCRIBE
    assert "_commit_run_with_progress" in INBOX
    assert "st.progress" in IMPORT
    assert "Writing export files" in Path("src/transcribe/ui/export_panel.py").read_text(
        encoding="utf-8"
    )
    assert TRANSCRIBE.count("_render_ocr_settings_form(") == 2
    assert 'key_prefix="tx"' in TRANSCRIBE
    assert 'key_prefix="tx_batch"' not in TRANSCRIBE
    assert "queue_transcribe_imported" in INBOX
    assert "Transcribe imported notebooks" in INBOX


def test_ocr_batch_run_format_registered() -> None:
    assert SUPPORTED.get("transcribe.ocr-batch-run") == 1
    contract = Path("docs/contracts/ocr-batch-run.md").read_text(encoding="utf-8")
    assert "transcribe.ocr-batch-run" in contract
    assert "JobCoordinator" in contract
    assert "MultiPassCoordinator" in contract
    assert "mode" in contract
    assert "vision_model_names" in contract
    assert "Multipass / compare-models over a batch" not in contract
