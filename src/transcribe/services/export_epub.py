"""EPUB export writer (requires ebooklib)."""

from __future__ import annotations

import html
from pathlib import Path

from transcribe.services.export_document import ExportDocument, document_css
from transcribe.services.export_options import ExportOptions


class EpubDependencyError(RuntimeError):
    """Raised when EPUB export is requested but ebooklib is not installed."""


def _require_ebooklib():
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError as exc:  # pragma: no cover - env dependent
        raise EpubDependencyError(
            "EPUB export requires ebooklib. Install with: pip install -e '.[export]'"
        ) from exc
    return ebooklib, epub


def _section_body(text: str) -> str:
    if not text.strip():
        return '<p class="blank">(blank page)</p>'
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        return "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())
    out: list[str] = []
    for block in blocks:
        out.append(f"<p>{html.escape(block).replace(chr(10), '<br/>')}</p>")
    return "\n".join(out)


def build_epub(document: ExportDocument, options: ExportOptions) -> bytes:
    _ebooklib, epub = _require_ebooklib()
    book = epub.EpubBook()
    book.set_identifier(f"transcribe-{document.stamp_revision[:16]}")
    book.set_title(document.title)
    book.set_language("en")
    book.add_metadata(
        "DC",
        "description",
        f"transcribe.content_revision: {document.stamp_revision}",
    )
    book.add_metadata("DC", "creator", "Transcribe")

    css = document_css(options)
    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=css.encode("utf-8"),
    )
    book.add_item(style)

    spine: list = ["nav"]
    toc: list = []
    chapters: list = []

    if options.title_page:
        title_html = (
            f"<html><head><link rel='stylesheet' href='style/default.css'/></head>"
            f"<body><h1>{html.escape(document.title)}</h1>"
            f"<p class='revision'>transcribe.content_revision: "
            f"{html.escape(document.stamp_revision)}</p></body></html>"
        )
        title_ch = epub.EpubHtml(
            title="Title",
            file_name="title.xhtml",
            lang="en",
            content=title_html,
        )
        title_ch.add_item(style)
        book.add_item(title_ch)
        spine.append(title_ch)
        chapters.append(title_ch)

    for part_i, part in enumerate(document.parts):
        part_toc: list = []
        if document.is_bundle or options.title_page:
            part_html = (
                f"<html><head><link rel='stylesheet' href='style/default.css'/></head>"
                f"<body><h1>{html.escape(part.title)}</h1>"
            )
            if part.date_start_label or part.date_end_label:
                span = " – ".join(x for x in (part.date_start_label, part.date_end_label) if x)
                part_html += f"<p class='meta'>{html.escape(span)}</p>"
            part_html += "</body></html>"
            part_ch = epub.EpubHtml(
                title=part.title,
                file_name=f"part-{part_i}-{part.slug}.xhtml",
                lang="en",
                content=part_html,
            )
            part_ch.add_item(style)
            book.add_item(part_ch)
            spine.append(part_ch)
            chapters.append(part_ch)
            part_toc.append(part_ch)

        for sec_i, section in enumerate(part.sections):
            heading = section.label
            if section.date_label:
                heading = f"{heading} · {section.date_label}"
            tag = "h2"
            body = (
                f"<html><head><link rel='stylesheet' href='style/default.css'/></head>"
                f"<body><{tag}>{html.escape(heading)}</{tag}>"
                f"{_section_body(section.text)}</body></html>"
            )
            ch = epub.EpubHtml(
                title=section.label,
                file_name=f"part-{part_i}-page-{sec_i}.xhtml",
                lang="en",
                content=body,
            )
            ch.add_item(style)
            book.add_item(ch)
            spine.append(ch)
            chapters.append(ch)
            part_toc.append(ch)

        if document.is_bundle and part_toc:
            toc.append((epub.Section(part.title), part_toc))
        else:
            toc.extend(part_toc)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    # Write to bytes via temp path pattern — ebooklib writes to file.
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        epub.write_epub(str(tmp_path), book, {})
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def write_epub(path: Path, document: ExportDocument, options: ExportOptions) -> None:
    path.write_bytes(build_epub(document, options))
