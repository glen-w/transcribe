"""Notebook content_revision — exportable notebook identity (not analysis fingerprint)."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.domain.models import PageResult, Project

CONTENT_REVISION_VERSION = 1


def build_content_revision_object(
    project: Project,
    results: Mapping[str, PageResult | None],
) -> dict[str, Any]:
    """Canonical object whose hash is content_revision (export membership = all pages)."""
    pages: list[dict[str, Any]] = []
    for global_index, page in enumerate(project.pages):
        result = results.get(page.page_id)
        text = result.effective_text() if result is not None else None
        edited = bool(result is not None and result.edited_text is not None)
        status = result.status if result is not None else "pending"
        pages.append(
            {
                "page_id": page.page_id,
                "global_index": global_index,
                "text": text,
                "edited": edited,
                "status": status,
                "date": page.date.as_dict() if page.date else None,
                "date_approved": bool(page.date_approved),
                "date_source": page.date_source,
                "tags": sorted(str(t) for t in (page.tags or ())),
            }
        )
    return {
        "content_revision_version": CONTENT_REVISION_VERSION,
        "project_id": project.id,
        "pages": pages,
    }


def content_revision_hex(
    project: Project,
    results: Mapping[str, PageResult | None],
) -> str:
    """SHA-256 hex of the canonical notebook content revision object."""
    return hashlib.sha256(
        canonical_json_bytes(build_content_revision_object(project, results))
    ).hexdigest()


def content_revision_from_pages(
    *,
    project_id: str,
    pages: Sequence[Mapping[str, Any]],
) -> str:
    """Compute revision from already-normalized page dicts (tests / adapters)."""
    body = {
        "content_revision_version": CONTENT_REVISION_VERSION,
        "project_id": project_id,
        "pages": list(pages),
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()
