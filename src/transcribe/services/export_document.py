"""Format-agnostic export document IR built from one or more snapshots."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Sequence

from transcribe.domain.fingerprint import canonical_json_bytes
from transcribe.domain.models import PageResult, Project
from transcribe.services.export_options import ExportOptions


@dataclass(frozen=True)
class ExportSnapshot:
    """Frozen project + page-result view for coherent multi-format export."""

    project: Project
    results: dict[str, PageResult | None]
    content_revision: str = ""


def _slugify(title: str, fallback: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").strip().lower()).strip("-")
    return (raw or fallback)[:64]


def format_page_date(page_date: dict[str, Any] | None) -> str | None:
    if not page_date:
        return None
    y = page_date.get("year")
    m = page_date.get("month")
    d = page_date.get("day")
    if y is None:
        return None
    if m is None:
        return str(y)
    if d is None:
        return f"{y}-{int(m):02d}"
    return f"{y}-{int(m):02d}-{int(d):02d}"


@dataclass(frozen=True)
class ExportSection:
    """One notebook page in the export IR."""

    page_id: str
    label: str
    text: str
    date_label: str | None = None
    blank: bool = False


@dataclass(frozen=True)
class ExportPart:
    """One notebook (chapter group) in the export IR."""

    project_id: str
    title: str
    content_revision: str
    slug: str
    date_start_label: str | None = None
    date_end_label: str | None = None
    sections: tuple[ExportSection, ...] = ()


@dataclass(frozen=True)
class ExportDocument:
    """Anthology or single-notebook document ready for writers."""

    title: str
    bundle_revision: str
    parts: tuple[ExportPart, ...] = ()
    application_version: str = ""

    @property
    def is_bundle(self) -> bool:
        return len(self.parts) > 1

    @property
    def primary_project_id(self) -> str:
        return self.parts[0].project_id if self.parts else ""

    @property
    def stamp_revision(self) -> str:
        """Revision hex stamped into human-readable artifacts.

        Single-notebook exports keep using the notebook ``content_revision`` for
        backward compatibility; anthologies use ``bundle_revision``.
        """
        if len(self.parts) == 1:
            return self.parts[0].content_revision
        return self.bundle_revision


def bundle_revision_hex(part_revisions: Sequence[tuple[str, str]]) -> str:
    """Hash ordered (project_id, content_revision) pairs into a bundle revision."""
    body = {
        "bundle_revision_version": 1,
        "parts": [
            {"project_id": pid, "content_revision": rev} for pid, rev in part_revisions
        ],
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _page_date_dict(page: Any) -> dict[str, Any] | None:
    return page.date.as_dict() if page.date else None


def build_part_from_snapshot(
    snapshot: ExportSnapshot,
    options: ExportOptions,
    *,
    slug_fallback: str | None = None,
) -> ExportPart:
    project = snapshot.project
    sections: list[ExportSection] = []
    for i, page in enumerate(project.pages):
        result = snapshot.results.get(page.page_id)
        text = (result.effective_text() if result else None) or ""
        stripped = text.strip()
        blank = not stripped
        if blank and not options.include_blank_pages:
            continue
        date_label = None
        if options.include_dates:
            date_label = format_page_date(_page_date_dict(page))
        sections.append(
            ExportSection(
                page_id=page.page_id,
                label=f"Page {i + 1}",
                text=stripped,
                date_label=date_label,
                blank=blank,
            )
        )
    start_label = (
        format_page_date(project.date_start.as_dict() if project.date_start else None)
        if options.include_dates
        else None
    )
    end_label = (
        format_page_date(project.date_end.as_dict() if project.date_end else None)
        if options.include_dates
        else None
    )
    slug = _slugify(project.title, slug_fallback or project.id[:8])
    return ExportPart(
        project_id=project.id,
        title=project.title,
        content_revision=snapshot.content_revision,
        slug=slug,
        date_start_label=start_label,
        date_end_label=end_label,
        sections=tuple(sections),
    )


def build_document(
    snapshots: Sequence[ExportSnapshot],
    options: ExportOptions,
    *,
    application_version: str = "",
    title: str | None = None,
) -> ExportDocument:
    if not snapshots:
        raise ValueError("export requires at least one snapshot")
    parts: list[ExportPart] = []
    used_slugs: set[str] = set()
    for snap in snapshots:
        part = build_part_from_snapshot(snap, options)
        slug = part.slug
        if slug in used_slugs:
            slug = f"{slug}-{part.project_id[:8]}"
        used_slugs.add(slug)
        if slug != part.slug:
            part = ExportPart(
                project_id=part.project_id,
                title=part.title,
                content_revision=part.content_revision,
                slug=slug,
                date_start_label=part.date_start_label,
                date_end_label=part.date_end_label,
                sections=part.sections,
            )
        parts.append(part)
    rev = bundle_revision_hex([(p.project_id, p.content_revision) for p in parts])
    if title:
        doc_title = title
    elif len(parts) == 1:
        doc_title = parts[0].title
    else:
        doc_title = "Notebook anthology"
    return ExportDocument(
        title=doc_title,
        bundle_revision=rev,
        parts=tuple(parts),
        application_version=application_version,
    )


def document_css(options: ExportOptions) -> str:
    typo = options.typography
    return f"""
:root {{
  --body-font: {typo.css_font_family};
  --body-size: {typo.body_size_pt}pt;
  --line-height: {typo.line_height};
  --para-spacing: {typo.paragraph_spacing_em}em;
  --heading-scale: {typo.heading_scale};
  --margin: {typo.margin_in}in;
}}
body {{
  font-family: var(--body-font);
  font-size: var(--body-size);
  line-height: var(--line-height);
  margin: var(--margin);
  color: #111;
}}
h1 {{
  font-size: calc(var(--body-size) * var(--heading-scale) * 1.4);
  font-weight: 600;
  margin: 0 0 1em;
}}
h2 {{
  font-size: calc(var(--body-size) * var(--heading-scale) * 1.15);
  font-weight: 600;
  margin: 1.4em 0 0.6em;
  page-break-before: always;
}}
h2:first-of-type {{ page-break-before: avoid; }}
h3 {{
  font-size: calc(var(--body-size) * var(--heading-scale));
  font-weight: 600;
  margin: 1.2em 0 0.4em;
}}
p {{
  margin: 0 0 var(--para-spacing);
}}
.meta, .revision {{
  color: #555;
  font-size: 0.9em;
}}
.part-title-page {{
  margin: 2em 0 2em;
}}
.section {{
  {"page-break-before: always;" if options.page_breaks == "per_page" else ""}
}}
.blank {{
  color: #888;
  font-style: italic;
}}
""".strip()
