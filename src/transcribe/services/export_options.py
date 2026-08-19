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
PdfBaseFamily = Literal["serif", "sans", "mono"]
PageBreakMode = Literal["per_page", "continuous"]

# PyMuPDF Base-14 font names for PDF output (named fonts map to nearest base).
PDF_FONT_BY_BASE: dict[PdfBaseFamily, str] = {
    "serif": "times-roman",
    "sans": "helv",
    "mono": "cour",
}


@dataclass(frozen=True)
class BodyFontSpec:
    """One selectable export body font."""

    key: str
    label: str
    css_stack: str
    pdf_base: PdfBaseFamily
    google_family: str | None = None


def _spec(
    key: str,
    label: str,
    css_stack: str,
    pdf_base: PdfBaseFamily,
    *,
    google_family: str | None = None,
) -> BodyFontSpec:
    return BodyFontSpec(
        key=key,
        label=label,
        css_stack=css_stack,
        pdf_base=pdf_base,
        google_family=google_family,
    )


# Curated free / system fonts for HTML, EPUB, and PDF (PDF uses nearest Base-14).
BODY_FONT_CATALOG: dict[str, BodyFontSpec] = {
    spec.key: spec
    for spec in (
        _spec(
            "serif",
            "System serif",
            'Georgia, "Times New Roman", Times, serif',
            "serif",
        ),
        _spec(
            "georgia",
            "Georgia",
            'Georgia, "Times New Roman", Times, serif',
            "serif",
        ),
        _spec(
            "times_new_roman",
            "Times New Roman",
            '"Times New Roman", Times, Georgia, serif',
            "serif",
        ),
        _spec(
            "garamond",
            "Garamond",
            'Garamond, "Times New Roman", Georgia, serif',
            "serif",
        ),
        _spec(
            "merriweather",
            "Merriweather",
            '"Merriweather", Georgia, "Times New Roman", serif',
            "serif",
            google_family="Merriweather",
        ),
        _spec(
            "lora",
            "Lora",
            '"Lora", Georgia, "Times New Roman", serif',
            "serif",
            google_family="Lora",
        ),
        _spec(
            "libre_baskerville",
            "Libre Baskerville",
            '"Libre Baskerville", Georgia, "Times New Roman", serif',
            "serif",
            google_family="Libre Baskerville",
        ),
        _spec(
            "crimson_text",
            "Crimson Text",
            '"Crimson Text", Georgia, "Times New Roman", serif',
            "serif",
            google_family="Crimson Text",
        ),
        _spec(
            "source_serif_pro",
            "Source Serif Pro",
            '"Source Serif Pro", Georgia, "Times New Roman", serif',
            "serif",
            google_family="Source Serif Pro",
        ),
        _spec(
            "sans",
            "System sans",
            'system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
            "sans",
        ),
        _spec(
            "arial",
            "Arial",
            'Arial, Helvetica, "Segoe UI", sans-serif',
            "sans",
        ),
        _spec(
            "verdana",
            "Verdana",
            'Verdana, Geneva, "Segoe UI", sans-serif',
            "sans",
        ),
        _spec(
            "trebuchet",
            "Trebuchet MS",
            '"Trebuchet MS", "Segoe UI", Helvetica, sans-serif',
            "sans",
        ),
        _spec(
            "open_sans",
            "Open Sans",
            '"Open Sans", system-ui, "Segoe UI", sans-serif',
            "sans",
            google_family="Open Sans",
        ),
        _spec(
            "roboto",
            "Roboto",
            'Roboto, system-ui, "Segoe UI", Helvetica, sans-serif',
            "sans",
            google_family="Roboto",
        ),
        _spec(
            "lato",
            "Lato",
            'Lato, system-ui, "Segoe UI", Helvetica, sans-serif',
            "sans",
            google_family="Lato",
        ),
        _spec(
            "inter",
            "Inter",
            'Inter, system-ui, "Segoe UI", Helvetica, sans-serif',
            "sans",
            google_family="Inter",
        ),
        _spec(
            "nunito",
            "Nunito",
            'Nunito, system-ui, "Segoe UI", Helvetica, sans-serif',
            "sans",
            google_family="Nunito",
        ),
        _spec(
            "source_sans_pro",
            "Source Sans Pro",
            '"Source Sans Pro", system-ui, "Segoe UI", sans-serif',
            "sans",
            google_family="Source Sans Pro",
        ),
        _spec(
            "mono",
            "System mono",
            '"SF Mono", Consolas, "Liberation Mono", Menlo, monospace',
            "mono",
        ),
        _spec(
            "courier_new",
            "Courier New",
            '"Courier New", Courier, "Liberation Mono", monospace',
            "mono",
        ),
        _spec(
            "consolas",
            "Consolas",
            'Consolas, "SF Mono", "Liberation Mono", Menlo, monospace',
            "mono",
        ),
        _spec(
            "source_code_pro",
            "Source Code Pro",
            '"Source Code Pro", Consolas, "SF Mono", monospace',
            "mono",
            google_family="Source Code Pro",
        ),
        _spec(
            "ibm_plex_mono",
            "IBM Plex Mono",
            '"IBM Plex Mono", Consolas, "SF Mono", monospace',
            "mono",
            google_family="IBM Plex Mono",
        ),
        _spec(
            "jetbrains_mono",
            "JetBrains Mono",
            '"JetBrains Mono", Consolas, "SF Mono", monospace',
            "mono",
            google_family="JetBrains Mono",
        ),
    )
}

BODY_FONT_CHOICES: tuple[str, ...] = tuple(BODY_FONT_CATALOG.keys())
DEFAULT_BODY_FONT = "serif"
BodyFont = str


def normalize_body_font(value: str | None) -> str:
    key = str(value or DEFAULT_BODY_FONT).lower().strip()
    if key in BODY_FONT_CATALOG:
        return key
    return DEFAULT_BODY_FONT


def body_font_spec(key: str) -> BodyFontSpec:
    return BODY_FONT_CATALOG[normalize_body_font(key)]


def body_font_label(key: str) -> str:
    return body_font_spec(key).label

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
        font = normalize_body_font(str(data.get("body_font") or DEFAULT_BODY_FONT))
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
    def font_spec(self) -> BodyFontSpec:
        return body_font_spec(self.body_font)

    @property
    def pdf_fontname(self) -> str:
        return PDF_FONT_BY_BASE[self.font_spec.pdf_base]

    @property
    def css_font_family(self) -> str:
        return self.font_spec.css_stack

    @property
    def google_fonts_css_import(self) -> str:
        family = self.font_spec.google_family
        if not family:
            return ""
        query = family.replace(" ", "+")
        return (
            f"@import url('https://fonts.googleapis.com/css2?"
            f"family={query}&display=swap');"
        )


@dataclass(frozen=True)
class ExportOptions:
    formats: frozenset[ExportFormat] = field(default_factory=lambda: DEFAULT_FORMATS)
    page_breaks: PageBreakMode = "per_page"
    include_dates: bool = True
    include_blank_pages: bool = True
    exclude_ignored_pages: bool = True
    title_page: bool = True
    cover_image: bool = True
    typography: ExportTypography = field(default_factory=ExportTypography)

    def as_dict(self) -> dict[str, Any]:
        return {
            "formats": sorted(self.formats),
            "page_breaks": self.page_breaks,
            "include_dates": self.include_dates,
            "include_blank_pages": self.include_blank_pages,
            "exclude_ignored_pages": self.exclude_ignored_pages,
            "title_page": self.title_page,
            "cover_image": self.cover_image,
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
            exclude_ignored_pages=bool(data.get("exclude_ignored_pages", True)),
            title_page=bool(data.get("title_page", True)),
            cover_image=bool(data.get("cover_image", True)),
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
    exclude_ignored_pages: bool = True
    title_page: bool = True
    cover_image: bool = True
    typography: ExportTypography = field(default_factory=ExportTypography)

    def as_dict(self) -> dict[str, Any]:
        return {
            "formats": list(self.formats),
            "page_breaks": self.page_breaks,
            "include_dates": self.include_dates,
            "include_blank_pages": self.include_blank_pages,
            "exclude_ignored_pages": self.exclude_ignored_pages,
            "title_page": self.title_page,
            "cover_image": self.cover_image,
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
            exclude_ignored_pages=opts.exclude_ignored_pages,
            title_page=opts.title_page,
            cover_image=opts.cover_image,
            typography=opts.typography,
        )

    def to_options(self) -> ExportOptions:
        return ExportOptions.from_dict(self.as_dict())
