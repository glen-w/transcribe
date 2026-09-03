"""People names from published NER (PERSON) for the names detector."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from transcribe.tagging.kernel import normalize_slug

NER_PEOPLE_PROMPT_ID = "ner:people"
SOURCE_MODULE = "ner"
PERSON_LABEL = "PERSON"


def _page_id_from_entity(row: dict[str, Any]) -> str | None:
    ref = row.get("source_ref")
    if isinstance(ref, dict):
        pid = ref.get("page_id")
        if isinstance(pid, str) and pid:
            return pid
    unit_id = row.get("unit_id")
    if isinstance(unit_id, str) and unit_id:
        return unit_id
    return None


def _fold_surface(surface: str) -> str:
    return " ".join(surface.strip().split()).casefold()


@dataclass(frozen=True)
class PageNameHit:
    """Distinct PERSON surface on one page, ready to tag."""

    page_id: str
    surface: str
    slug: str
    count: int
    samples: tuple[str, ...]


def page_person_names(payload: dict[str, Any] | None) -> list[PageNameHit]:
    """Group PERSON entities by (page_id, normalized slug); first surface wins."""
    if not isinstance(payload, dict):
        return []
    entities = payload.get("entities")
    if not isinstance(entities, list):
        return []

    counts: dict[tuple[str, str], int] = defaultdict(int)
    surfaces: dict[tuple[str, str], str] = {}
    samples: dict[tuple[str, str], list[str]] = defaultdict(list)
    seen_sample: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in entities:
        if not isinstance(row, dict):
            continue
        if row.get("label") != PERSON_LABEL:
            continue
        surface = row.get("surface") or row.get("text")
        if not isinstance(surface, str) or not surface.strip():
            continue
        page_id = _page_id_from_entity(row)
        if not page_id:
            continue
        slug = normalize_slug(surface)
        if not slug:
            continue
        key = (page_id, slug)
        counts[key] += 1
        if key not in surfaces:
            surfaces[key] = surface.strip()
        folded = _fold_surface(surface)
        if folded and folded not in seen_sample[key]:
            seen_sample[key].add(folded)
            samples[key].append(surface.strip())

    hits = [
        PageNameHit(
            page_id=page_id,
            surface=surfaces[(page_id, slug)],
            slug=slug,
            count=counts[(page_id, slug)],
            samples=tuple(samples[(page_id, slug)][:8]),
        )
        for page_id, slug in counts
    ]
    hits.sort(key=lambda h: (h.page_id, h.slug))
    return hits


def filter_hits_to_pages(
    hits: list[PageNameHit],
    page_ids: set[str] | frozenset[str],
) -> list[PageNameHit]:
    if not page_ids:
        return []
    return [h for h in hits if h.page_id in page_ids]


def published_ner_is_current(
    published: dict[str, Any] | None,
    planned_cache_identity: str | None,
) -> bool:
    if published is None or not planned_cache_identity:
        return False
    if published.get("cache_identity") != planned_cache_identity:
        return False
    return str(published.get("outcome") or "") in {
        "success",
        "skipped_not_applicable",
        "insufficient_data",
        "unavailable_dependency",
    }
