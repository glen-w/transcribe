"""Parse Altair/Vega point selections from activity histogram clicks."""

from __future__ import annotations

BIN_SELECT = "bin_select"


def selected_bin_label(event: object) -> str | None:
    """Extract the clicked bin ``label`` from an Altair ``on_select`` event."""
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return None
    points = None
    if isinstance(selection, dict):
        points = selection.get(BIN_SELECT)
    else:
        points = getattr(selection, BIN_SELECT, None)
        if points is None and hasattr(selection, "get"):
            points = selection.get(BIN_SELECT)
    if not points or isinstance(points, dict):
        return None
    if not isinstance(points, (list, tuple)):
        return None
    first = points[0] if points else None
    if not isinstance(first, dict):
        return None
    label = first.get("label")
    return str(label) if label else None
