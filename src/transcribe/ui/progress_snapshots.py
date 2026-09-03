"""Pure progress → panel snapshot mapping (no Streamlit widgets)."""

from __future__ import annotations

from typing import Any

from transcribe.services.batch_analysis import BatchAnalysisProgress
from transcribe.services.batch_ocr import BatchOcrProgress
from transcribe.services.job import JobProgress


def job_progress_to_snapshot(progress: JobProgress) -> dict[str, Any]:
    done = progress.completed + progress.failed
    total = progress.total
    pct = (done / total * 100.0) if total else 0.0
    if progress.status == "completed":
        if progress.circuit_open:
            panel_status, phase = "completed", "partial"
        else:
            panel_status, phase = "completed", "completed"
        pct = 100.0 if total else pct
    elif progress.status == "failed":
        panel_status, phase = "failed", "failed"
    elif progress.status == "cancelled":
        panel_status, phase = "cancelled", "cancelled"
    else:
        panel_status, phase = "running", "running_pipeline"
    current = ", ".join(progress.current_labels) or ", ".join(
        p[:8] for p in progress.current_page_ids
    )
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": current,
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.message if progress.status == "failed" else None,
    }


def batch_ocr_progress_to_snapshot(progress: BatchOcrProgress) -> dict[str, Any]:
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    page_frac = 0.0
    if progress.status == "running" and progress.pages_total:
        page_done = progress.pages_completed + progress.pages_failed
        page_frac = min(1.0, page_done / progress.pages_total)
    pct = ((done + page_frac) / total * 100.0) if total else 0.0
    status = progress.status
    if status == "completed":
        panel_status, phase = "completed", "completed"
        pct = 100.0 if total else pct
    elif status == "partial":
        panel_status, phase = "completed", "partial"
    elif status == "cancelled":
        panel_status, phase = "cancelled", "cancelled"
    elif status == "failed":
        panel_status, phase = "failed", "failed"
    else:
        panel_status, phase = "running", "running_pipeline"
    detail_bits: list[str] = []
    if progress.mode == "multipass":
        if progress.phase:
            detail_bits.append(progress.phase)
        if progress.current_model:
            detail_bits.append(progress.current_model)
        elif progress.model_total:
            detail_bits.append(f"model {progress.model_index}/{progress.model_total}")
    if progress.current_page_label:
        detail_bits.append(progress.current_page_label)
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": progress.current_item,
        "detail_current": " · ".join(detail_bits) if detail_bits else "",
        "detail_completed": progress.pages_completed,
        "detail_failed": progress.pages_failed,
        "detail_skipped": progress.pages_skipped,
        "detail_total": progress.pages_total,
        "detail_unit": "pages in this notebook",
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.message if status == "failed" else None,
    }


def batch_analysis_progress_to_snapshot(progress: BatchAnalysisProgress) -> dict[str, Any]:
    """Map BatchAnalysisProgress into the shared progress panel snapshot."""
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    module_frac = 0.0
    if progress.status == "running" and progress.modules_total:
        module_done = progress.modules_completed + progress.modules_failed
        module_frac = min(1.0, module_done / progress.modules_total)
    pct = ((done + module_frac) / total * 100.0) if total else 0.0
    status = progress.status
    if status == "completed":
        panel_status, phase = "completed", "completed"
        pct = 100.0 if total else pct
    elif status == "partial":
        panel_status, phase = "completed", "partial"
    elif status == "cancelled":
        panel_status, phase = "cancelled", "cancelled"
    elif status == "failed":
        panel_status, phase = "failed", "failed"
    else:
        panel_status, phase = "running", "running_pipeline"
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": progress.current_item,
        "current_module": progress.current_module_id,
        "detail_current": progress.current_module_id,
        "detail_completed": progress.modules_completed,
        "detail_failed": progress.modules_failed,
        "detail_skipped": progress.modules_skipped,
        "detail_total": progress.modules_total,
        "detail_unit": "modules in this notebook",
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.error
        if status == "failed"
        else (progress.message if status == "failed" else None),
    }
