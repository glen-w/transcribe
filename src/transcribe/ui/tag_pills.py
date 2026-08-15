"""Colored organisation-tag chips and clickable viewer pills."""

from __future__ import annotations

import hashlib
import html
from collections.abc import Sequence

import streamlit as st

from transcribe.tagging.kernel import TagCatalog, display_tag, normalize_slugs, pill_text_color


def _pill_key(prefix: str, slug: str) -> str:
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def tags_html(slugs: Sequence[str], catalog: TagCatalog) -> str:
    parts: list[str] = []
    for slug in normalize_slugs(list(slugs)):
        tag = display_tag(catalog, slug)
        text = pill_text_color(tag)
        label = html.escape(tag.label)
        parts.append(
            f'<span class="tx-tag-pill" style="background:{html.escape(tag.color)};'
            f'color:{text}">{label}</span>'
        )
    return " ".join(parts)


def render_tag_chips(slugs: Sequence[str], catalog: TagCatalog) -> None:
    markup = tags_html(slugs, catalog)
    if markup:
        st.markdown(markup, unsafe_allow_html=True)


def render_clickable_pills(
    slugs: Sequence[str],
    *,
    catalog: TagCatalog,
    selected: Sequence[str],
    key_prefix: str,
) -> str | None:
    """Render clickable pills. Returns the slug that was clicked, if any."""
    tokens = normalize_slugs(list(slugs))
    if not tokens:
        return None
    selected_set = set(normalize_slugs(list(selected)))
    styles: list[str] = []
    clicked: str | None = None
    cols = st.columns(min(len(tokens), 8))
    for i, slug in enumerate(tokens):
        tag = display_tag(catalog, slug)
        key = _pill_key(key_prefix, slug)
        text = pill_text_color(tag)
        active = slug in selected_set
        border = "2px solid #111" if active else "1px solid rgba(0,0,0,0.18)"
        styles.append(
            f'[class*="st-key-{key}"] button {{'
            f"background:{tag.color} !important;color:{text} !important;"
            f"border:{border} !important;border-radius:999px !important;"
            f"padding:0.15rem 0.7rem !important;font-weight:600 !important;"
            f"font-size:0.8rem !important;min-height:1.7rem !important;"
            f"}}"
        )
        label = f"✓ {tag.label}" if active else tag.label
        if cols[i % len(cols)].button(label, key=key, help=f"Filter to pages tagged {tag.label}"):
            clicked = slug
    if styles:
        st.markdown("<style>" + "".join(styles) + "</style>", unsafe_allow_html=True)
    return clicked


def render_tag_assignment_editor(
    *,
    current: Sequence[str],
    catalog: TagCatalog,
    key_prefix: str,
) -> tuple[list[str], str]:
    """Multiselect of catalogue slugs plus a free-text add field."""
    current_slugs = normalize_slugs(list(current))
    options = [t.slug for t in catalog.tags]
    for slug in current_slugs:
        if slug not in options:
            options.append(slug)
    labels = {t.slug: t.label for t in catalog.tags}
    for slug in options:
        labels.setdefault(slug, slug)
    selected = st.multiselect(
        "Tags",
        options=options,
        default=[s for s in current_slugs if s in options],
        format_func=lambda s: labels.get(s, s),
        key=f"{key_prefix}_select",
        help="Choose existing tags. Add new names below.",
    )
    new_raw = st.text_input(
        "Add tags (comma-separated)",
        value="",
        key=f"{key_prefix}_new",
        help="New names are added to the workspace catalogue.",
    )
    return list(selected), new_raw
