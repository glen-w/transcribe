"""Export presentation options (formats, typography, structure)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

ExportFormat = Literal["json", "markdown", "text", "html", "epub", "pdf"]
EXPORT_FORMATS: tuple[ExportFormat, ...] = (
    "json",
    "markdown",
    "text",
    "html",
    "epub",
    "pdf",
)
BodyFont = Literal["serif", "sans", "mono"]
PageBreakMode = Literal["per_page", "continuous"]

# PyMuPDF Base-14 font names for PDF output.
PDF_FONT_BY_BODY: dict[BodyFont, str] = {
    "serif": "times-roman",
    "sans": "helv",
    "mono": "cour",
}

# CSS generic families for HTML/EPUB.
CSS_FONT_BY_BODY: dict[BodyFont, str] = {
    "serif": 'Georgia, "Times New Roman", Times, serif',
    "sans": 'system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    "mono": '"SF Mono", Consolas, "Liberation Mono", Menlo, monospace',
}

DEFAULT_FORMATS: frozenset[ExportFormat] = frozenset(
    {"json", "markdown", "text", "html", "epub", "pdf"}
)


@dataclass(frozen=True)
class ExportTypography:
    body_font: BodyFont = "serif"
    body_size_pt: float = 11.0
    line_height: float = 1.45
    paragraph_spacing_em: float = 0.6
    margin_in: float = 0.75
    heading_scale: float = 1.25

    def as_dict(self) -> dict[str, Any]:
        return {
            "body_font": self.body_font,
            "body_size_pt": self.body_size_pt,
            "line_height": self.line_height,
            "paragraph_spacing_em": self.paragraph_spacing_em,
            "margin_in": self.margin_in,
            "heading_scale": self.heading_scale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ExportTypography:
        data = data or {}
        font = str(data.get("body_font") or "serif").lower()
        if font not in ("serif", "sans", "mono"):
            font = "serif"
        size = float(data.get("body_size_pt", 11.0))
        size = max(8.0, min(28.0, size))
        line_height = float(data.get("line_height", 1.45))
        line_height = max(1.0, min(3.0, line_height))
        para = float(data.get("paragraph_spacing_em", 0.6))
        para = max(0.0, min(3.0, para))
        margin = float(data.get("margin_in", 0.75))
        margin = max(0.25, min(2.0, margin))
        heading = float(data.get("heading_scale", 1.25))
        heading = max(1.0, min(2.5, heading))
        return cls(
            body_font=font,  # type: ignore[arg-type]
            body_size_pt=size,
            line_height=line_height,
            paragraph_spacing_em=para,
            margin_in=margin,
            heading_scale=heading,
        )

    @property
    def pdf_fontname(self) -> str:
        return PDF_FONT_BY_BODY[self.body_font]

    @property
    def css_font_family(self) -> str:
        return CSS_FONT_BY_BODY[self.body_font]


@dataclass(frozen=True)
class ExportOptions:
    formats: frozenset[ExportFormat] = field(default_factory=lambda: DEFAULT_FORMATS)
    page_breaks: PageBreakMode = "per_page"
    include_dates: bool = True
    include_blank_pages: bool = True
    title_page: bool = True
    typography: ExportTypography = field(default_factory=ExportTypography)

    def as_dict(self) -> dict[str, Any]:
        return {
            "formats": sorted(self.formats),
            "page_breaks": self.page_breaks,
            "include_dates": self.include_dates,
            "include_blank_pages": self.include_blank_pages,
            "title_page": self.title_page,
            "typography": self.typography.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ExportOptions:
        data = data or {}
        raw_formats = data.get("formats")
        if raw_formats is None:
            formats: frozenset[ExportFormat] = DEFAULT_FORMATS
        else:
            chosen: set[ExportFormat] = set()
            for item in raw_formats:
                key = str(item).lower()
                if key in EXPORT_FORMATS:
                    chosen.add(key)  # type: ignore[arg-type]
            formats = frozenset(chosen) if chosen else DEFAULT_FORMATS
        breaks = str(data.get("page_breaks") or "per_page").lower()
        if breaks not in ("per_page", "continuous"):
            breaks = "per_page"
        return cls(
            formats=formats,
            page_breaks=breaks,  # type: ignore[arg-type]
            include_dates=bool(data.get("include_dates", True)),
            include_blank_pages=bool(data.get("include_blank_pages", True)),
            title_page=bool(data.get("title_page", True)),
            typography=ExportTypography.from_dict(data.get("typography")),
        )

    def wants(self, fmt: ExportFormat) -> bool:
        return fmt in self.formats


@dataclass(frozen=True)
class ExportConfig:
    """Workspace ``export`` config subtree (mirrors ExportOptions)."""

    formats: tuple[str, ...] = field(default_factory=lambda: tuple(sorted(DEFAULT_FORMATS)))
    page_breaks: PageBreakMode = "per_page"
    include_dates: bool = True
    include_blank_pages: bool = True
    title_page: bool = True
    typography: ExportTypography = field(default_factory=ExportTypography)

    def as_dict(self) -> dict[str, Any]:
        return {
            "formats": list(self.formats),
            "page_breaks": self.page_breaks,
            "include_dates": self.include_dates,
            "include_blank_pages": self.include_blank_pages,
            "title_page": self.title_page,
            "typography": self.typography.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ExportConfig:
        opts = ExportOptions.from_dict(data)
        return cls(
            formats=tuple(sorted(opts.formats)),
            page_breaks=opts.page_breaks,
            include_dates=opts.include_dates,
            include_blank_pages=opts.include_blank_pages,
            title_page=opts.title_page,
            typography=opts.typography,
        )

    def to_options(self) -> ExportOptions:
        return ExportOptions.from_dict(self.as_dict())
