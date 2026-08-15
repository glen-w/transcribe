"""Organisation tagging.

Copy-boundary (TranscriptX Theme F later): ``kernel.py`` and ``colors.py`` are
host-agnostic stdlib modules (relative imports only). ``store.py`` is Transcribe
persistence and must not be copied as-is.
"""

from .colors import (
    DEFAULT_PALETTE,
    contrast_text_color,
    default_color_for_slug,
    parse_hex_color,
)
from .kernel import (
    FORMAT,
    SCHEMA_VERSION,
    RewritePlan,
    TagCatalog,
    TagDef,
    TagError,
    apply_rewrite,
    catalog_from_payload,
    change_slug,
    constrain_entries,
    delete_tag,
    display_tag,
    ensure_slugs,
    ensure_tag,
    filter_ids,
    merge_tags,
    normalize_slug,
    normalize_slugs,
    pill_text_color,
    recolor,
    rename_label,
    snapshot_for_slugs,
)

__all__ = [
    "DEFAULT_PALETTE",
    "FORMAT",
    "SCHEMA_VERSION",
    "RewritePlan",
    "TagCatalog",
    "TagDef",
    "TagError",
    "apply_rewrite",
    "catalog_from_payload",
    "change_slug",
    "constrain_entries",
    "contrast_text_color",
    "default_color_for_slug",
    "delete_tag",
    "display_tag",
    "ensure_slugs",
    "ensure_tag",
    "filter_ids",
    "merge_tags",
    "normalize_slug",
    "normalize_slugs",
    "parse_hex_color",
    "pill_text_color",
    "recolor",
    "rename_label",
    "snapshot_for_slugs",
]
