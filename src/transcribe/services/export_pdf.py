"""PDF export writer using PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from transcribe.services.export_document import ExportDocument, ExportPart, ExportSection
from transcribe.services.export_options import ExportOptions

# A4 in points
_PAGE_W = 595.0
_PAGE_H = 842.0


class _PdfBuilder:
    def __init__(self, document: ExportDocument, options: ExportOptions) -> None:
        self.document = document
        self.options = options
        self.typo = options.typography
        self.doc = pymupdf.open()
        self.margin = self.typo.margin_in * 72.0
        self.fontsize = self.typo.body_size_pt
        self.heading_size = self.fontsize * self.typo.heading_scale
        self.title_size = self.heading_size * 1.4
        self.leading = self.fontsize * self.typo.line_height
        self.fontname = self.typo.pdf_fontname
        self.page: pymupdf.Page | None = None
        self.y = 0.0

    def _content_rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(
            self.margin,
            self.margin,
            _PAGE_W - self.margin,
            _PAGE_H - self.margin,
        )

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.y = self.margin

    def _ensure_space(self, needed: float) -> None:
        if self.page is None:
            self._new_page()
            return
        if self.y + needed > _PAGE_H - self.margin:
            self._new_page()

    def _write_textbox(
        self,
        text: str,
        *,
        fontsize: float,
        fontname: str | None = None,
        bold_as_heading: bool = False,
    ) -> None:
        if not text:
            return
        font = fontname or self.fontname
        # Approximate height needed; insert_textbox handles wrapping.
        width = _PAGE_W - 2 * self.margin
        # Rough line estimate
        chars_per_line = max(20, int(width / (fontsize * 0.5)))
        lines = max(1, (len(text) + chars_per_line - 1) // chars_per_line)
        est_h = lines * fontsize * self.typo.line_height + 4
        self._ensure_space(min(est_h, _PAGE_H - 2 * self.margin))
        assert self.page is not None
        remaining = text
        while remaining:
            rect = pymupdf.Rect(
                self.margin,
                self.y,
                _PAGE_W - self.margin,
                _PAGE_H - self.margin,
            )
            if rect.height < fontsize * 1.2:
                self._new_page()
                continue
            overflow = self.page.insert_textbox(
                rect,
                remaining,
                fontsize=fontsize,
                fontname=font,
                align=pymupdf.TEXT_ALIGN_LEFT,
                lineheight=self.typo.line_height,
            )
            if overflow >= 0:
                # Unused space returned — advance by used height approx
                used = rect.height - overflow
                self.y += max(used, fontsize * self.typo.line_height)
                break
            # Negative overflow: text did not fit; advance page with what fit.
            # insert_textbox with negative means characters that did not fit.
            # Re-flow by taking a prefix that fits is awkward; use TextWriter-less
            # approach: write what we can by splitting on paragraphs.
            # Fall back: new page and retry if nothing written (y near bottom).
            if self.y <= self.margin + 1:
                # Entire page couldn't fit one chunk — force write truncated line
                self.page.insert_text(
                    (self.margin, self.y + fontsize),
                    remaining[: chars_per_line * 40],
                    fontsize=fontsize,
                    fontname=font,
                )
                break
            self._new_page()
        del bold_as_heading  # reserved for future weight mapping

    def _gap(self, em: float) -> None:
        self._ensure_space(self.fontsize * em)
        self.y += self.fontsize * em

    def add_title_page(self) -> None:
        self._new_page()
        self._write_textbox(self.document.title, fontsize=self.title_size)
        self._gap(0.8)
        if self.document.is_bundle:
            self._write_textbox(
                f"{len(self.document.parts)} notebooks",
                fontsize=self.fontsize,
            )
            self._gap(0.4)
        self._write_textbox(
            f"transcribe.content_revision: {self.document.stamp_revision}",
            fontsize=self.fontsize * 0.85,
        )

    def add_part_heading(self, part: ExportPart) -> None:
        if self.options.page_breaks == "per_page" or self.page is not None:
            self._new_page()
        else:
            self._ensure_space(self.heading_size * 3)
        self._write_textbox(part.title, fontsize=self.heading_size * 1.15)
        self._gap(0.4)
        if part.date_start_label or part.date_end_label:
            span = " – ".join(
                x for x in (part.date_start_label, part.date_end_label) if x
            )
            self._write_textbox(span, fontsize=self.fontsize * 0.9)
            self._gap(0.3)
        if self.document.is_bundle:
            self._write_textbox(
                part.content_revision,
                fontsize=self.fontsize * 0.8,
            )
            self._gap(0.5)

    def add_section(self, section: ExportSection, *, use_h3: bool) -> None:
        if self.options.page_breaks == "per_page":
            self._new_page()
        else:
            self._gap(self.typo.paragraph_spacing_em)
        heading = section.label
        if section.date_label:
            heading = f"{heading} · {section.date_label}"
        size = self.heading_size if not use_h3 else self.heading_size * 0.95
        self._write_textbox(heading, fontsize=size)
        self._gap(0.35)
        body = section.text if section.text else "(blank page)"
        # Split paragraphs for spacing
        paras = [p.strip() for p in body.split("\n\n")] or [body]
        for i, para in enumerate(paras):
            if not para:
                continue
            self._write_textbox(para, fontsize=self.fontsize)
            if i < len(paras) - 1:
                self._gap(self.typo.paragraph_spacing_em)

    def build(self) -> bytes:
        if self.options.title_page:
            self.add_title_page()
        for part in self.document.parts:
            if self.document.is_bundle or self.options.title_page:
                self.add_part_heading(part)
            elif self.page is None:
                self._new_page()
            for section in part.sections:
                self.add_section(section, use_h3=self.document.is_bundle)
        if self.doc.page_count == 0:
            self._new_page()
        self.doc.set_metadata(
            {
                "title": self.document.title,
                "creator": "Transcribe",
                "subject": f"transcribe.content_revision:{self.document.stamp_revision}",
            }
        )
        return self.doc.tobytes(deflate=True)


def build_pdf(document: ExportDocument, options: ExportOptions) -> bytes:
    builder = _PdfBuilder(document, options)
    try:
        return builder.build()
    finally:
        builder.doc.close()


def write_pdf(path: Path, document: ExportDocument, options: ExportOptions) -> None:
    path.write_bytes(build_pdf(document, options))
