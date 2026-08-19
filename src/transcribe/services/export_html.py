"""HTML export writer."""

from __future__ import annotations

import html
from pathlib import Path

from transcribe.services.export_document import (
    ExportDocument,
    ExportPart,
    cover_image_data_uri,
    document_css,
)
from transcribe.services.export_options import ExportOptions


def _cover_html(part: ExportPart, *, alt: str) -> str:
    path = part.cover_image_path
    if path is None or not path.is_file():
        return ""
    src = cover_image_data_uri(path)
    return (
        f'<figure class="cover-image">'
        f'<img src="{src}" alt="{html.escape(alt)}"/>'
        f"</figure>"
    )


def _p(text: str) -> str:
    if not text.strip():
        return '<p class="blank">(blank page)</p>'
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        lines = text.splitlines() or [text]
        return "".join(f"<p>{html.escape(line)}</p>\n" for line in lines if line.strip())
    out: list[str] = []
    for block in blocks:
        escaped = html.escape(block).replace("\n", "<br/>\n")
        out.append(f"<p>{escaped}</p>")
    return "\n".join(out)


def build_html(document: ExportDocument, options: ExportOptions) -> str:
    parts_html: list[str] = []
    rev = document.stamp_revision
    if options.cover_image and len(document.parts) == 1:
        cover = _cover_html(document.parts[0], alt=document.title)
        if cover:
            parts_html.append(cover)
    if options.title_page:
        parts_html.append('<header class="title-page">')
        parts_html.append(f"<h1>{html.escape(document.title)}</h1>")
        if document.is_bundle:
            parts_html.append(f'<p class="meta">{len(document.parts)} notebooks</p>')
        parts_html.append(
            f'<p class="revision">transcribe.content_revision: {html.escape(rev)}</p>'
        )
        parts_html.append("</header>")

    for part in document.parts:
        if options.cover_image and document.is_bundle:
            cover = _cover_html(part, alt=part.title)
            if cover:
                parts_html.append(cover)
        if document.is_bundle or options.title_page:
            parts_html.append('<section class="part-title-page">')
            parts_html.append(f"<h2>{html.escape(part.title)}</h2>")
            if part.date_start_label or part.date_end_label:
                span = " – ".join(x for x in (part.date_start_label, part.date_end_label) if x)
                parts_html.append(f'<p class="meta">{html.escape(span)}</p>')
            if document.is_bundle:
                parts_html.append(f'<p class="revision">{html.escape(part.content_revision)}</p>')
            parts_html.append("</section>")

        for section in part.sections:
            parts_html.append(f'<section class="section" id="{html.escape(section.page_id)}">')
            heading = section.label
            if section.date_label:
                heading = f"{heading} · {section.date_label}"
            tag = "h3" if document.is_bundle else "h2"
            parts_html.append(f"<{tag}>{html.escape(heading)}</{tag}>")
            parts_html.append(_p(section.text))
            parts_html.append("</section>")

    body = "\n".join(parts_html)
    css = document_css(options)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        f"<title>{html.escape(document.title)}</title>\n"
        f"<style>\n{css}\n</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def write_html(path: Path, document: ExportDocument, options: ExportOptions) -> None:
    path.write_bytes(build_html(document, options).encode("utf-8"))
