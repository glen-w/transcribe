"""Organisation-tag kernel — host-agnostic (stdlib only).

Copy-boundary: this module plus ``colors.py`` may be copied into TranscriptX.
Do not import ``transcribe.*`` or ``transcriptx.*``.

Assignments on host entities stay ``list[str]`` of **slugs**. The catalog owns
``tag_id``, display **label**, and **color**. Renaming a label does not rewrite
assignments; changing or merging slugs returns a :class:`RewritePlan`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .colors import (
    contrast_text_color,
    default_color_for_slug,
    parse_hex_color,
)

FORMAT = "personal_corpus.tag-catalog"
SCHEMA_VERSION = 1


class TagError(ValueError):
    """Invalid catalog operation (duplicate slug, unknown id, bad colour)."""


@dataclass(frozen=True)
class TagDef:
    tag_id: str
    slug: str
    label: str
    color: str
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "tag_id": self.tag_id,
            "slug": self.slug,
            "label": self.label,
            "color": self.color,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TagDef:
        return cls(
            tag_id=str(data.get("tag_id") or ""),
            slug=str(data.get("slug") or ""),
            label=str(data.get("label") or ""),
            color=str(data.get("color") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class TagCatalog:
    tags: list[TagDef] = field(default_factory=list)
    updated_at: str = ""

    def by_id(self) -> dict[str, TagDef]:
        return {t.tag_id: t for t in self.tags if t.tag_id}

    def by_slug(self) -> dict[str, TagDef]:
        return {t.slug: t for t in self.tags if t.slug}

    def get_by_id(self, tag_id: str) -> TagDef | None:
        return self.by_id().get(tag_id)

    def get_by_slug(self, slug: str) -> TagDef | None:
        return self.by_slug().get(slug)

    def as_dict(self) -> dict[str, object]:
        return {
            "format": FORMAT,
            "schema_version": SCHEMA_VERSION,
            "updated_at": self.updated_at,
            "tags": [t.as_dict() for t in self.tags],
        }


@dataclass(frozen=True)
class RewritePlan:
    """Host applies ``mapping`` to every assignment list (slug → new slug or drop)."""

    mapping: dict[str, str | None]

    def is_empty(self) -> bool:
        return not self.mapping


def normalize_slug(raw: str | None) -> str:
    """Single-token slug: trim, lowercase, collapse whitespace."""
    if raw is None:
        return ""
    return " ".join(str(raw).strip().lower().split())


def normalize_slugs(tags: Iterable[str] | None) -> list[str]:
    """Ordered unique slugs (first-seen wins). Empty / blank inputs dropped."""
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        token = normalize_slug(raw)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _require_id(catalog: TagCatalog, tag_id: str) -> TagDef:
    tag = catalog.get_by_id(tag_id)
    if tag is None:
        raise TagError(f"unknown tag_id: {tag_id}")
    return tag


def _with_tags(catalog: TagCatalog, tags: list[TagDef], *, now_iso: str) -> TagCatalog:
    return TagCatalog(tags=list(tags), updated_at=now_iso)


def display_tag(catalog: TagCatalog, slug: str) -> TagDef:
    """Catalog entry, or an ephemeral def for an uncatalogued assignment slug."""
    token = normalize_slug(slug)
    found = catalog.get_by_slug(token)
    if found is not None:
        return found
    color = default_color_for_slug(token or "tag")
    return TagDef(
        tag_id="",
        slug=token,
        label=token or slug,
        color=color,
    )


def ensure_tag(
    catalog: TagCatalog,
    raw: str,
    *,
    new_id: Callable[[], str],
    now_iso: str,
    color: str | None = None,
    label: str | None = None,
) -> tuple[TagCatalog, TagDef, bool]:
    """Return catalog + tag. Creates when the slug is new.

    ``label`` defaults to the trimmed original text (not lowercased) so
    ``Poetry`` stores slug ``poetry`` with label ``Poetry``.
    """
    slug = normalize_slug(raw)
    if not slug:
        raise TagError("tag slug is empty")
    existing = catalog.get_by_slug(slug)
    if existing is not None:
        return catalog, existing, False
    if color is None:
        hex_color = default_color_for_slug(slug)
    else:
        hex_color = parse_hex_color(color)
    display = (label or str(raw).strip() or slug).strip() or slug
    tag = TagDef(
        tag_id=new_id(),
        slug=slug,
        label=display,
        color=hex_color,
        created_at=now_iso,
        updated_at=now_iso,
    )
    tags = list(catalog.tags)
    tags.append(tag)
    return _with_tags(catalog, tags, now_iso=now_iso), tag, True


def ensure_slugs(
    catalog: TagCatalog,
    slugs: Sequence[str],
    *,
    new_id: Callable[[], str],
    now_iso: str,
    labels: Mapping[str, str] | None = None,
    colors: Mapping[str, str] | None = None,
) -> tuple[TagCatalog, list[TagDef]]:
    """Ensure each slug exists. Returns the final catalog and resolved defs."""
    labels = labels or {}
    colors = colors or {}
    current = catalog
    resolved: list[TagDef] = []
    for raw in slugs:
        slug = normalize_slug(raw)
        if not slug:
            continue
        current, tag, _ = ensure_tag(
            current,
            raw,
            new_id=new_id,
            now_iso=now_iso,
            color=colors.get(slug),
            label=labels.get(slug),
        )
        resolved.append(tag)
    return current, resolved


def rename_label(
    catalog: TagCatalog,
    tag_id: str,
    new_label: str,
    *,
    now_iso: str,
) -> TagCatalog:
    """Change display label only — assignments (slugs) stay put."""
    tag = _require_id(catalog, tag_id)
    label = str(new_label).strip()
    if not label:
        raise TagError("tag label is empty")
    if label == tag.label:
        return catalog
    updated = TagDef(
        tag_id=tag.tag_id,
        slug=tag.slug,
        label=label,
        color=tag.color,
        created_at=tag.created_at,
        updated_at=now_iso,
    )
    tags = [updated if t.tag_id == tag_id else t for t in catalog.tags]
    return _with_tags(catalog, tags, now_iso=now_iso)


def recolor(
    catalog: TagCatalog,
    tag_id: str,
    color: str,
    *,
    now_iso: str,
) -> TagCatalog:
    tag = _require_id(catalog, tag_id)
    hex_color = parse_hex_color(color)
    if hex_color == tag.color:
        return catalog
    updated = TagDef(
        tag_id=tag.tag_id,
        slug=tag.slug,
        label=tag.label,
        color=hex_color,
        created_at=tag.created_at,
        updated_at=now_iso,
    )
    tags = [updated if t.tag_id == tag_id else t for t in catalog.tags]
    return _with_tags(catalog, tags, now_iso=now_iso)


def change_slug(
    catalog: TagCatalog,
    tag_id: str,
    new_slug: str,
    *,
    now_iso: str,
) -> tuple[TagCatalog, RewritePlan]:
    """Rename the assignment key. Host must apply the rewrite plan."""
    tag = _require_id(catalog, tag_id)
    slug = normalize_slug(new_slug)
    if not slug:
        raise TagError("tag slug is empty")
    if slug == tag.slug:
        return catalog, RewritePlan(mapping={})
    clash = catalog.get_by_slug(slug)
    if clash is not None and clash.tag_id != tag_id:
        raise TagError(f"slug already in use: {slug}")
    updated = TagDef(
        tag_id=tag.tag_id,
        slug=slug,
        label=tag.label,
        color=tag.color,
        created_at=tag.created_at,
        updated_at=now_iso,
    )
    tags = [updated if t.tag_id == tag_id else t for t in catalog.tags]
    return _with_tags(catalog, tags, now_iso=now_iso), RewritePlan(mapping={tag.slug: slug})


def merge_tags(
    catalog: TagCatalog,
    source_id: str,
    target_id: str,
    *,
    now_iso: str,
) -> tuple[TagCatalog, RewritePlan]:
    """Rewrite source assignments onto target and drop the source catalog entry."""
    if source_id == target_id:
        raise TagError("cannot merge a tag into itself")
    source = _require_id(catalog, source_id)
    target = _require_id(catalog, target_id)
    tags = [t for t in catalog.tags if t.tag_id != source_id]
    target_updated = TagDef(
        tag_id=target.tag_id,
        slug=target.slug,
        label=target.label,
        color=target.color,
        created_at=target.created_at,
        updated_at=now_iso,
    )
    tags = [target_updated if t.tag_id == target_id else t for t in tags]
    return (
        _with_tags(catalog, tags, now_iso=now_iso),
        RewritePlan(mapping={source.slug: target.slug}),
    )


def delete_tag(
    catalog: TagCatalog,
    tag_id: str,
    *,
    now_iso: str,
) -> tuple[TagCatalog, RewritePlan]:
    """Drop the catalog entry and strip the slug from assignments."""
    tag = _require_id(catalog, tag_id)
    tags = [t for t in catalog.tags if t.tag_id != tag_id]
    return _with_tags(catalog, tags, now_iso=now_iso), RewritePlan(mapping={tag.slug: None})


def apply_rewrite(slugs: Sequence[str], plan: RewritePlan) -> list[str]:
    """Apply a slug rewrite to one assignment list (deduped, first-seen order)."""
    if plan.is_empty():
        return normalize_slugs(slugs)
    seen: set[str] = set()
    out: list[str] = []
    for raw in slugs:
        token = normalize_slug(raw)
        if not token:
            continue
        if token in plan.mapping:
            dest = plan.mapping[token]
            if dest is None:
                continue
            token = normalize_slug(dest)
            if not token:
                continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def filter_ids(
    items: Sequence[tuple[str, Sequence[str]]],
    required_slugs: Sequence[str],
    *,
    mode: str = "and",
) -> list[str]:
    """Return item ids whose assignment lists match ``required_slugs``.

    ``mode="and"``: every required slug must be present (Archive/viewer).
    ``mode="or"``: any required slug is enough.
    Empty ``required_slugs`` returns every id.
    """
    needed = normalize_slugs(required_slugs)
    if not needed:
        return [item_id for item_id, _ in items]
    op = mode.strip().lower()
    out: list[str] = []
    for item_id, assigned in items:
        have = set(normalize_slugs(assigned))
        if op == "or":
            if any(s in have for s in needed):
                out.append(item_id)
        else:
            if all(s in have for s in needed):
                out.append(item_id)
    return out


def constrain_entries(
    entries: Sequence[Mapping[str, str]],
    page_tags_by_id: Mapping[str, Sequence[str]],
    required_slugs: Sequence[str],
) -> list[dict[str, str]]:
    """Keep viewer entries whose page tags contain all ``required_slugs`` (AND)."""
    needed = normalize_slugs(required_slugs)
    if not needed:
        return [{"page_id": e["page_id"], "project_root": e["project_root"]} for e in entries]
    kept: list[dict[str, str]] = []
    for entry in entries:
        page_id = str(entry.get("page_id") or "")
        root = str(entry.get("project_root") or "")
        if not page_id or not root:
            continue
        have = set(normalize_slugs(page_tags_by_id.get(page_id) or ()))
        if all(s in have for s in needed):
            kept.append({"page_id": page_id, "project_root": root})
    return kept


def snapshot_for_slugs(catalog: TagCatalog, slugs: Sequence[str]) -> list[dict[str, str]]:
    """Catalog (or ephemeral) defs for export — only slugs that are assigned."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in slugs:
        token = normalize_slug(raw)
        if not token or token in seen:
            continue
        seen.add(token)
        tag = display_tag(catalog, token)
        out.append(tag.as_dict())
    return out


def pill_text_color(tag: TagDef) -> str:
    return contrast_text_color(tag.color)


def catalog_from_payload(payload: Mapping[str, object] | None) -> TagCatalog:
    """Parse a catalog object. Caller validates format/version separately."""
    if not payload:
        return TagCatalog()
    raw_tags = payload.get("tags") or []
    tags: list[TagDef] = []
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    if isinstance(raw_tags, list):
        for row in raw_tags:
            if not isinstance(row, Mapping):
                continue
            try:
                tag = TagDef.from_dict(row)
                tag = TagDef(
                    tag_id=tag.tag_id,
                    slug=normalize_slug(tag.slug),
                    label=(tag.label.strip() or tag.slug),
                    color=(
                        parse_hex_color(tag.color)
                        if tag.color
                        else default_color_for_slug(tag.slug)
                    ),
                    created_at=tag.created_at,
                    updated_at=tag.updated_at,
                )
            except (TypeError, ValueError, TagError):
                continue
            if not tag.tag_id or not tag.slug:
                continue
            if tag.tag_id in seen_ids or tag.slug in seen_slugs:
                continue
            seen_ids.add(tag.tag_id)
            seen_slugs.add(tag.slug)
            tags.append(tag)
    return TagCatalog(tags=tags, updated_at=str(payload.get("updated_at") or ""))
