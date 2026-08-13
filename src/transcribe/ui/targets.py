"""Session keys for Import / Transcribe Target switchers (TranscriptX-style)."""

from __future__ import annotations

from typing import Any

ANALYSE_TARGET_KEY = "analyse_target"
PENDING_ANALYSE_TARGET_KEY = "pending_analyse_target"
ANALYSE_BATCH_NOTEBOOK_IDS_KEY = "analyse_batch_notebook_ids"
ANALYSE_BATCH_IMPORT_RUN_KEY = "analyse_batch_import_run_id"
ANALYSE_BATCH_SOURCE_KEY = "analyse_batch_source"

TARGET_THIS = "This notebook"
TARGET_BATCH = "Batch"
TARGET_OPTIONS = (TARGET_THIS, TARGET_BATCH)

IMPORT_TARGET_KEY = "import_target"
TRANSCRIBE_TARGET_KEY = "transcribe_target"
PENDING_IMPORT_TARGET_KEY = "pending_import_target"
PENDING_TRANSCRIBE_TARGET_KEY = "pending_transcribe_target"
TRANSCRIBE_BATCH_NOTEBOOK_IDS_KEY = "transcribe_batch_notebook_ids"
TRANSCRIBE_BATCH_IMPORT_RUN_KEY = "transcribe_batch_import_run_id"
TRANSCRIBE_BATCH_SOURCE_KEY = "transcribe_batch_source"


def apply_pending_target(session: Any, *, pending_key: str, target_key: str) -> None:
    """Copy a queued Target into the widget key before the control binds."""
    pending = session.pop(pending_key, None)
    if pending in TARGET_OPTIONS:
        session[target_key] = pending


def normalize_target(session: Any, key: str) -> str:
    current = session.get(key)
    if current in TARGET_OPTIONS:
        return str(current)
    session[key] = TARGET_THIS
    return TARGET_THIS
