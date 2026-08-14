"""Parse Altair/Vega point selections from clickable page-series charts."""

from __future__ import annotations

PAGE_SELECT = "page_select"


def selected_page_id(event: object) -> str | None:
    """Extract the clicked ``page_id`` from an Altair ``on_select`` event."""
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return None
    points = None
    if isinstance(selection, dict):
        points = selection.get(PAGE_SELECT)
    else:
        points = getattr(selection, PAGE_SELECT, None)
        if points is None and hasattr(selection, "get"):
            points = selection.get(PAGE_SELECT)
    if not points or isinstance(points, dict):
        return None
    if not isinstance(points, (list, tuple)):
        return None
    first = points[0] if points else None
    if not isinstance(first, dict):
        return None
    page_id = first.get("page_id")
    return str(page_id) if page_id else None


def page_id_from_unit_id(unit_id: str | None) -> str | None:
    """Map analysis ``unit_id`` to a notebook ``page_id``.

    page_v1 unit ids equal page ids; paragraph_v1 uses ``{page_id}/span:…``.
    """
    if not isinstance(unit_id, str) or not unit_id:
        return None
    if "/span:" in unit_id:
        return unit_id.split("/span:", 1)[0] or None
    return unit_id
