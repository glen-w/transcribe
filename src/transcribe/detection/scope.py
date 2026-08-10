"""Detection scope and window planning."""

from __future__ import annotations

import hashlib

from transcribe.detection.definition import DetectorDefinition, DetectorScope
from transcribe.detection.inputs import PageInput, WindowInput
from transcribe.domain.fingerprint import canonical_json_bytes


def plan_windows(
    detector: DetectorDefinition,
    page_inputs: list[PageInput],
) -> list[WindowInput]:
    if not page_inputs:
        return []
    ordered = sorted(page_inputs, key=lambda p: p.page_order_index)
    scope = detector.scope
    if scope == DetectorScope.PAGE:
        return [_single_window(p) for p in ordered]

    size = max(1, detector.window_size)
    overlap = max(0, min(detector.window_overlap, size - 1))
    step = max(1, size - overlap)
    windows: list[WindowInput] = []
    for start in range(0, len(ordered), step):
        chunk = ordered[start : start + size]
        if not chunk:
            break
        if scope == DetectorScope.PAGE_WINDOW and len(chunk) < size and start > 0:
            # trailing partial window still valid at notebook end
            pass
        windows.append(_build_window(chunk))
        if start + size >= len(ordered):
            break
    return windows


def _single_window(page: PageInput) -> WindowInput:
    return _build_window([page])


def _build_window(pages: list[PageInput]) -> WindowInput:
    labels = []
    parts = []
    for i, p in enumerate(pages):
        label = f"PAGE {i + 1} (id={p.page_id})"
        labels.append(label)
        parts.append(f"{label}\n{p.effective_text}")
    page_ids = tuple(p.page_id for p in pages)
    wid_payload = {"page_ids": list(page_ids)}
    window_id = hashlib.sha256(canonical_json_bytes(wid_payload)).hexdigest()[:16]
    return WindowInput(
        window_id=window_id,
        page_ids=page_ids,
        pages=tuple(pages),
        combined_text="\n\n---\n\n".join(parts),
        page_labels=", ".join(labels),
    )
