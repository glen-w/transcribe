"""Places from NER: extract place labels, optional Nominatim geocode + local cache.

Maps are a read-model over published ``ner`` payloads — not a new analysis module.
Network geocoding is opt-in; cached coordinates work fully offline.

Alignment with TranscriptX (no runtime dependency — copy patterns only):
- Place candidates: TX uses GPE|LOC for maps; Transcribe also includes FAC
  (buildings/landmarks common in handwritten notebooks).
- Geocode: Nominatim, ≥1s between live lookups, frequency-ranked cap, durable
  cache including misses (TX ``location_cache.py``).
- Artifact: ``analysis/ner/locations.json`` mirrors TX ``ner-locations`` for
  notebook domain (page provenance instead of speaker/segment timing).
- Intentional divergences: opt-in privacy (TX defaults geocoding on), stdlib
  urllib instead of geopy, Streamlit ``st.map`` instead of Folium/[maps] extra.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.dates import ApproximateDate
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import FileLock
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import discover_project_roots
from transcribe.services.project import open_project_paths

# TranscriptX map filter (parity).
PLACE_LABELS_TX = frozenset({"GPE", "LOC"})
# Notebook adaptation: FAC covers museums/buildings that diaries often name.
PLACE_LABELS = PLACE_LABELS_TX | {"FAC"}
PERSON_LABEL = "PERSON"

GEOCODE_CACHE_SCHEMA = "transcribe.geocode-cache"
GEOCODE_CACHE_VERSION = 1
LOCATIONS_ARTIFACT_SCHEMA = "transcribe.ner-locations"
LOCATIONS_ARTIFACT_VERSION = 1
LOCATIONS_FILENAME = "locations.json"

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim requires an identifying User-Agent (TX uses geopy user_agent="transcriptx").
_USER_AGENT = (
    "TranscribeNotebookOCR/0.2 (local-first; places map; " "https://github.com/glen-w/transcribe)"
)
_MIN_REQUEST_INTERVAL_S = 1.05
_DEFAULT_TIMEOUT_S = 10.0  # match TX geopy timeout
_DEFAULT_MAX_NETWORK_LOOKUPS = 50  # match TX max_locations default

_WS_RE = re.compile(r"\s+")
_CACHEABLE_STATUSES = frozenset({"ok", "not_found", "error"})


def normalize_place_query(surface: str) -> str:
    """Stable cache key / geocode query for a NER surface form."""
    return _WS_RE.sub(" ", (surface or "").strip()).casefold()


@dataclass(frozen=True)
class PlaceMention:
    """One distinct place surface within a notebook (or corpus aggregate)."""

    surface: str
    label: str
    count: int
    page_ids: tuple[str, ...] = ()
    notebook_id: str | None = None
    notebook_title: str | None = None
    sample_quote: str | None = None


@dataclass(frozen=True)
class PersonMention:
    surface: str
    count: int
    page_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageRef:
    """Notebook page metadata for people mention rendering."""

    page_index: int
    page_count: int
    date: ApproximateDate | None = None
    text: str = ""


@dataclass(frozen=True)
class PersonOccurrence:
    """One PERSON entity hit with provenance for the People panel."""

    surface: str
    page_id: str | None
    snippet: str
    date: ApproximateDate | None = None
    order: int = 0
    notebook_title: str | None = None
    project_root: Path | None = None


@dataclass(frozen=True)
class GeocodedPlace:
    surface: str
    query: str
    lat: float | None
    lon: float | None
    display_name: str | None
    status: str  # ok | not_found | error | pending | skipped
    label: str = "GPE"
    count: int = 1
    page_ids: tuple[str, ...] = ()
    notebook_id: str | None = None
    notebook_title: str | None = None
    provider: str | None = None
    message: str | None = None
    sample_quote: str | None = None


@dataclass
class PlacesSnapshot:
    """Places (+ optional people) derived from one or more NER payloads."""

    places: list[PlaceMention] = field(default_factory=list)
    people: list[PersonMention] = field(default_factory=list)
    ner_available: bool = False
    ner_outcome: str | None = None
    notebooks_scanned: int = 0
    notebooks_with_ner: int = 0


GeocodeFn = Callable[[str], dict[str, Any]]


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


def _quotes_from_evidence(evidence: list[Any] | None) -> dict[str, str]:
    """First quote per normalized place surface from NER evidence rows."""
    out: dict[str, str] = {}
    if not isinstance(evidence, list):
        return out
    for row in evidence:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        if label not in PLACE_LABELS:
            continue
        quote = row.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            continue
        key_src = row.get("surface") or row.get("text") or quote
        if not isinstance(key_src, str):
            continue
        key = normalize_place_query(key_src)
        if key and key not in out:
            out[key] = quote.strip()
    return out


def extract_from_ner_payload(
    payload: dict[str, Any] | None,
    *,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
    evidence: list[Any] | None = None,
) -> PlacesSnapshot:
    """Aggregate place/person surfaces from a published ``ner_payload_v1``."""
    if not isinstance(payload, dict):
        return PlacesSnapshot(ner_available=False)

    entities = payload.get("entities")
    if not isinstance(entities, list):
        return PlacesSnapshot(
            places=[],
            ner_available=True,
            ner_outcome="success",
            notebooks_scanned=1 if notebook_id else 0,
            notebooks_with_ner=1 if notebook_id else 0,
        )

    quotes = _quotes_from_evidence(evidence)
    place_pages: dict[tuple[str, str], set[str]] = defaultdict(set)
    place_counts: dict[tuple[str, str], int] = defaultdict(int)
    place_surface: dict[tuple[str, str], str] = {}
    person_pages: dict[str, set[str]] = defaultdict(set)
    person_counts: dict[str, int] = defaultdict(int)
    person_surface: dict[str, str] = {}

    for row in entities:
        if not isinstance(row, dict):
            continue
        surface = row.get("surface") or row.get("text")
        label = row.get("label")
        if not isinstance(surface, str) or not surface.strip():
            continue
        if not isinstance(label, str) or not label:
            continue
        key = normalize_place_query(surface)
        if not key:
            continue
        page_id = _page_id_from_entity(row)

        if label in PLACE_LABELS:
            pk = (key, label)
            place_counts[pk] += 1
            place_surface[pk] = surface.strip()
            if page_id:
                place_pages[pk].add(page_id)
        elif label == PERSON_LABEL:
            person_counts[key] += 1
            person_surface[key] = surface.strip()
            if page_id:
                person_pages[key].add(page_id)

    places_out = [
        PlaceMention(
            surface=place_surface[pk],
            label=pk[1],
            count=place_counts[pk],
            page_ids=tuple(sorted(place_pages[pk])),
            notebook_id=notebook_id,
            notebook_title=notebook_title,
            sample_quote=quotes.get(pk[0]),
        )
        for pk in sorted(place_counts.keys(), key=lambda k: (-place_counts[k], k[0], k[1]))
    ]
    people_out = [
        PersonMention(
            surface=person_surface[k],
            count=person_counts[k],
            page_ids=tuple(sorted(person_pages[k])),
        )
        for k in sorted(person_counts.keys(), key=lambda k: (-person_counts[k], k))
    ]
    return PlacesSnapshot(
        places=places_out,
        people=people_out,
        ner_available=True,
        ner_outcome="success",
        notebooks_scanned=1 if notebook_id else 0,
        notebooks_with_ner=1 if notebook_id else 0,
    )


def _merge_snapshots(parts: Iterable[PlacesSnapshot]) -> PlacesSnapshot:
    place_merge: dict[tuple[str, str], dict[str, Any]] = {}
    person_merge: dict[str, dict[str, Any]] = {}
    scanned = 0
    with_ner = 0
    any_ner = False

    for snap in parts:
        scanned += snap.notebooks_scanned
        with_ner += snap.notebooks_with_ner
        any_ner = any_ner or snap.ner_available
        for p in snap.places:
            key = (normalize_place_query(p.surface), p.label)
            slot = place_merge.get(key)
            if slot is None:
                place_merge[key] = {
                    "surface": p.surface,
                    "label": p.label,
                    "count": p.count,
                    "page_ids": set(p.page_ids),
                    "notebook_ids": {p.notebook_id} if p.notebook_id else set(),
                    "notebook_titles": ({p.notebook_title} if p.notebook_title else set()),
                    "sample_quote": p.sample_quote,
                }
            else:
                slot["count"] += p.count
                slot["page_ids"].update(p.page_ids)
                if p.notebook_id:
                    slot["notebook_ids"].add(p.notebook_id)
                if p.notebook_title:
                    slot["notebook_titles"].add(p.notebook_title)
                if not slot.get("sample_quote") and p.sample_quote:
                    slot["sample_quote"] = p.sample_quote
        for person in snap.people:
            key = normalize_place_query(person.surface)
            slot = person_merge.get(key)
            if slot is None:
                person_merge[key] = {
                    "surface": person.surface,
                    "count": person.count,
                    "page_ids": set(person.page_ids),
                }
            else:
                slot["count"] += person.count
                slot["page_ids"].update(person.page_ids)

    places = []
    for (_nk, label), slot in sorted(
        place_merge.items(), key=lambda kv: (-kv[1]["count"], kv[0][0], kv[0][1])
    ):
        titles = sorted(t for t in slot["notebook_titles"] if t)
        nids = sorted(i for i in slot["notebook_ids"] if i)
        places.append(
            PlaceMention(
                surface=slot["surface"],
                label=label,
                count=int(slot["count"]),
                page_ids=tuple(sorted(slot["page_ids"])),
                notebook_id=nids[0] if len(nids) == 1 else None,
                notebook_title=(
                    titles[0]
                    if len(titles) == 1
                    else (f"{len(titles)} notebooks" if titles else None)
                ),
                sample_quote=slot.get("sample_quote"),
            )
        )
    people = [
        PersonMention(
            surface=slot["surface"],
            count=int(slot["count"]),
            page_ids=tuple(sorted(slot["page_ids"])),
        )
        for _k, slot in sorted(person_merge.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    ]
    return PlacesSnapshot(
        places=places,
        people=people,
        ner_available=any_ner,
        ner_outcome="success" if with_ner else None,
        notebooks_scanned=scanned,
        notebooks_with_ner=with_ner,
    )


def load_notebook_places(project_root: Path) -> PlacesSnapshot:
    """Load places from a notebook's published NER result (if any)."""
    paths = open_project_paths(Path(project_root))
    storage = AnalysisStorage(paths)
    published = storage.read_published("ner")
    notebook_id = paths.root.name
    title = paths.root.name
    try:
        manifest = read_json(paths.manifest)
        if isinstance(manifest, dict):
            if isinstance(manifest.get("id"), str) and manifest["id"]:
                notebook_id = manifest["id"]
            if isinstance(manifest.get("title"), str) and manifest["title"].strip():
                title = manifest["title"].strip()
    except Exception:  # noqa: BLE001
        pass

    if published is None:
        return PlacesSnapshot(
            ner_available=False,
            ner_outcome=None,
            notebooks_scanned=1,
            notebooks_with_ner=0,
        )
    outcome = published.get("outcome")
    payload = published.get("payload") or {}
    if outcome != "success":
        return PlacesSnapshot(
            ner_available=True,
            ner_outcome=str(outcome) if outcome else None,
            notebooks_scanned=1,
            notebooks_with_ner=0,
        )
    evidence = published.get("evidence")
    snap = extract_from_ner_payload(
        payload if isinstance(payload, dict) else {},
        notebook_id=notebook_id,
        notebook_title=title,
        evidence=evidence if isinstance(evidence, list) else None,
    )
    return PlacesSnapshot(
        places=snap.places,
        people=snap.people,
        ner_available=True,
        ner_outcome="success",
        notebooks_scanned=1,
        notebooks_with_ner=1,
    )


def load_corpus_places(projects_dir: Path) -> PlacesSnapshot:
    """Aggregate places across all notebooks under the projects root."""
    parts: list[PlacesSnapshot] = []
    for root in discover_project_roots(Path(projects_dir)):
        parts.append(load_notebook_places(root))
    if not parts:
        return PlacesSnapshot()
    return _merge_snapshots(parts)


class GeocodeCache:
    """Workspace-scoped durable geocode cache under ``data/cache/geocode.json``.

    Aligned with TX ``location_cache.json`` intent (durable hits + misses) but
    versioned, normalized keys, and atomic writes.
    """

    def __init__(self, runtime: RuntimePaths) -> None:
        self.path = Path(runtime.data_dir) / "cache" / "geocode.json"
        self._lock = FileLock(self.path.with_suffix(".lock"), timeout=30.0)

    def _empty(self) -> dict[str, Any]:
        return {
            "format": GEOCODE_CACHE_SCHEMA,
            "schema_version": GEOCODE_CACHE_VERSION,
            "entries": {},
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = read_json(self.path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(data, dict):
            return self._empty()
        entries = data.get("entries")
        if not isinstance(entries, dict):
            data = self._empty()
        return data

    def get(self, query: str) -> dict[str, Any] | None:
        key = normalize_place_query(query)
        if not key:
            return None
        entries = self.load().get("entries") or {}
        row = entries.get(key)
        return row if isinstance(row, dict) else None

    def put(self, query: str, entry: dict[str, Any]) -> None:
        key = normalize_place_query(query)
        if not key:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = self.load()
            entries = dict(data.get("entries") or {})
            row = dict(entry)
            row["query"] = query.strip()
            row["normalized"] = key
            entries[key] = row
            data["format"] = GEOCODE_CACHE_SCHEMA
            data["schema_version"] = GEOCODE_CACHE_VERSION
            data["entries"] = entries
            write_json_atomic(self.path, data)


def nominatim_geocode(
    query: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Resolve a place name via OpenStreetMap Nominatim (network).

    Uses stdlib urllib (TX uses geopy.Nominatim) — same public API, no hard dep.
    """
    q = query.strip()
    if not q:
        return {"status": "not_found", "lat": None, "lon": None, "display_name": None}

    params = urllib.parse.urlencode(
        {
            "q": q,
            "format": "json",
            "limit": "1",
        }
    )
    url = f"{_NOMINATIM_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout_s) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "status": "error",
            "lat": None,
            "lon": None,
            "display_name": None,
            "message": str(exc),
            "provider": "nominatim",
        }

    if not isinstance(payload, list) or not payload:
        return {
            "status": "not_found",
            "lat": None,
            "lon": None,
            "display_name": None,
            "provider": "nominatim",
        }
    hit = payload[0]
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return {
            "status": "error",
            "lat": None,
            "lon": None,
            "display_name": None,
            "message": "invalid nominatim coordinates",
            "provider": "nominatim",
        }
    display = hit.get("display_name")
    return {
        "status": "ok",
        "lat": lat,
        "lon": lon,
        "display_name": display if isinstance(display, str) else None,
        "provider": "nominatim",
    }


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _geocoded_from_cache_or_skip(
    place: PlaceMention,
    *,
    query: str,
    cached: dict[str, Any] | None,
    allow_network: bool,
    budget_exhausted: bool,
) -> GeocodedPlace | None:
    """Return a GeocodedPlace when no live lookup is needed; else None."""
    if cached and cached.get("status") in _CACHEABLE_STATUSES:
        lat = _as_float(cached.get("lat"))
        lon = _as_float(cached.get("lon"))
        status = str(cached.get("status"))
        if status == "ok" and (lat is None or lon is None):
            status = "error"
        return GeocodedPlace(
            surface=place.surface,
            query=query,
            lat=lat,
            lon=lon,
            display_name=cached.get("display_name"),
            status=status,
            label=place.label,
            count=place.count,
            page_ids=place.page_ids,
            notebook_id=place.notebook_id,
            notebook_title=place.notebook_title,
            provider=cached.get("provider"),
            message=(
                cached.get("message")
                if status != "error"
                else (cached.get("message") or "cached ok entry missing coordinates")
            ),
            sample_quote=place.sample_quote,
        )

    if not allow_network or budget_exhausted:
        return GeocodedPlace(
            surface=place.surface,
            query=query,
            lat=None,
            lon=None,
            display_name=None,
            status="skipped" if not allow_network else "pending",
            label=place.label,
            count=place.count,
            page_ids=place.page_ids,
            notebook_id=place.notebook_id,
            notebook_title=place.notebook_title,
            message=(
                "Enable OpenStreetMap geocoding to resolve this place"
                if not allow_network
                else "Deferred (lookup budget reached this session)"
            ),
            sample_quote=place.sample_quote,
        )
    return None


def resolve_places(
    places: list[PlaceMention],
    cache: GeocodeCache,
    *,
    allow_network: bool = False,
    geocode_fn: GeocodeFn | None = None,
    max_network_lookups: int = _DEFAULT_MAX_NETWORK_LOOKUPS,
    sleep_fn: Callable[[float], None] | None = None,
) -> list[GeocodedPlace]:
    """Attach coordinates using cache first, then optional network geocoding.

    Frequency-ranks candidates before live lookups (TX ``max_locations`` pattern).
    """
    geocode = geocode_fn or nominatim_geocode
    sleeper = sleep_fn or time.sleep
    ordered = sorted(places, key=lambda p: (-int(p.count), normalize_place_query(p.surface)))
    out: list[GeocodedPlace] = []
    network_used = 0
    last_network_at = 0.0

    for place in ordered:
        query = place.surface.strip()
        cached = cache.get(query)
        early = _geocoded_from_cache_or_skip(
            place,
            query=query,
            cached=cached,
            allow_network=allow_network,
            budget_exhausted=network_used >= max_network_lookups,
        )
        if early is not None:
            out.append(early)
            continue

        elapsed = time.monotonic() - last_network_at
        if last_network_at and elapsed < _MIN_REQUEST_INTERVAL_S:
            sleeper(_MIN_REQUEST_INTERVAL_S - elapsed)

        result = geocode(query)
        last_network_at = time.monotonic()
        network_used += 1
        lat = _as_float(result.get("lat"))
        lon = _as_float(result.get("lon"))
        status = str(result.get("status") or "error")
        if status == "ok" and (lat is None or lon is None):
            status = "error"
            result = {
                **result,
                "status": status,
                "message": result.get("message") or "geocoder returned ok without coordinates",
            }
        entry = {
            "status": status,
            "lat": lat,
            "lon": lon,
            "display_name": result.get("display_name"),
            "provider": result.get("provider") or "nominatim",
            "message": result.get("message"),
            "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # TX caches hits and misses; also cache errors to avoid Nominatim hammering
        # on Streamlit reruns.
        if entry["status"] in _CACHEABLE_STATUSES:
            cache.put(query, entry)
        out.append(
            GeocodedPlace(
                surface=place.surface,
                query=query,
                lat=entry.get("lat"),
                lon=entry.get("lon"),
                display_name=entry.get("display_name"),
                status=str(entry["status"]),
                label=place.label,
                count=place.count,
                page_ids=place.page_ids,
                notebook_id=place.notebook_id,
                notebook_title=place.notebook_title,
                provider=entry.get("provider"),
                message=entry.get("message"),
                sample_quote=place.sample_quote,
            )
        )
    return out


def map_points(geocoded: list[GeocodedPlace]) -> list[dict[str, Any]]:
    """Rows suitable for ``st.map`` (lat/lon) plus tooltip metadata."""
    rows: list[dict[str, Any]] = []
    for g in geocoded:
        lat = _as_float(g.lat)
        lon = _as_float(g.lon)
        if g.status != "ok" or lat is None or lon is None:
            continue
        rows.append(
            {
                "lat": lat,
                "lon": lon,
                "surface": g.surface,
                "label": g.label,
                "count": g.count,
                "display_name": g.display_name or g.surface,
                "notebook": g.notebook_title or "",
            }
        )
    return rows


def build_ner_locations_artifact(
    geocoded: list[GeocodedPlace],
    *,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> dict[str, Any]:
    """TX ``ner-locations`` analogue for notebook domain (no speakers).

    TX shape is ``{speaker: [{name, lat, lon, sentence, segment_index, start}]}``.
    Notebooks use a flat ``places`` list with ``page_ids`` instead of timing fields.
    """
    places_out: list[dict[str, Any]] = []
    for g in geocoded:
        if g.status != "ok":
            continue
        lat = _as_float(g.lat)
        lon = _as_float(g.lon)
        if lat is None or lon is None:
            continue
        places_out.append(
            {
                "name": g.surface,
                "lat": lat,
                "lon": lon,
                "label": g.label,
                "count": g.count,
                "display_name": g.display_name or g.surface,
                "page_ids": list(g.page_ids),
                "sentence": g.sample_quote or "",
                "notebook_id": g.notebook_id or notebook_id,
                "notebook_title": g.notebook_title or notebook_title,
            }
        )
    return {
        "format": LOCATIONS_ARTIFACT_SCHEMA,
        "schema_version": LOCATIONS_ARTIFACT_VERSION,
        "notebook_id": notebook_id,
        "notebook_title": notebook_title,
        "provider": "nominatim",
        "places": places_out,
    }


def locations_artifact_path(project_root: Path) -> Path:
    return open_project_paths(Path(project_root)).analysis_dir / "ner" / LOCATIONS_FILENAME


def write_ner_locations_artifact(
    project_root: Path,
    geocoded: list[GeocodedPlace],
    *,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> Path | None:
    """Persist geocoded places beside published NER (TX always writes ner-locations)."""
    ok = [g for g in geocoded if g.status == "ok"]
    if not ok:
        return None
    path = locations_artifact_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_ner_locations_artifact(
        geocoded,
        notebook_id=notebook_id,
        notebook_title=notebook_title,
    )
    write_json_atomic(path, payload)
    return path


def load_notebook_places_from_paths(paths: ProjectPaths) -> PlacesSnapshot:
    return load_notebook_places(paths.root)


def _date_from_entity_row(row: dict[str, Any]) -> ApproximateDate | None:
    raw = row.get("date")
    if isinstance(raw, dict):
        return ApproximateDate.from_dict(raw)
    return None


def _evidence_for_entity(
    entity: dict[str, Any], evidence: list[Any] | None
) -> dict[str, Any] | None:
    if not isinstance(evidence, list):
        return None
    unit_id = entity.get("unit_id")
    char_start = entity.get("char_start")
    char_end = entity.get("char_end")
    fallback: dict[str, Any] | None = None
    for row in evidence:
        if not isinstance(row, dict):
            continue
        if row.get("label") != PERSON_LABEL:
            continue
        if row.get("unit_id") != unit_id:
            continue
        if row.get("char_start") == char_start and row.get("char_end") == char_end:
            return row
        if fallback is None:
            fallback = row
    return fallback


def _person_snippet(
    surface: str,
    *,
    page_text: str | None,
    evidence_quote: str | None,
) -> str:
    from transcribe.services.archive import _snippet

    if page_text:
        return _snippet(page_text, surface)
    if evidence_quote:
        return evidence_quote.strip()
    return surface.strip()


def extract_person_occurrences(
    payload: dict[str, Any] | None,
    *,
    evidence: list[Any] | None = None,
    notebook_title: str | None = None,
    project_root: Path | None = None,
    page_refs: dict[str, PageRef] | None = None,
) -> dict[str, list[PersonOccurrence]]:
    """Group PERSON entity hits by normalized surface (sorted by date, page order)."""
    if not isinstance(payload, dict):
        return {}
    entities = payload.get("entities")
    if not isinstance(entities, list):
        return {}

    refs = page_refs or {}
    grouped: dict[str, list[PersonOccurrence]] = defaultdict(list)

    for row in entities:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        surface = row.get("surface") or row.get("text")
        if label != PERSON_LABEL or not isinstance(surface, str) or not surface.strip():
            continue
        page_id = _page_id_from_entity(row)
        ev = _evidence_for_entity(row, evidence)
        page_ref = refs.get(page_id) if page_id else None
        page_text = page_ref.text if page_ref else None
        ev_quote = ev.get("quote") if isinstance(ev, dict) else None
        if not isinstance(ev_quote, str):
            ev_quote = None
        snippet = _person_snippet(surface, page_text=page_text, evidence_quote=ev_quote)
        entity_date = _date_from_entity_row(row)
        date = entity_date or (page_ref.date if page_ref else None)
        order = row.get("order")
        grouped[normalize_place_query(surface)].append(
            PersonOccurrence(
                surface=surface.strip(),
                page_id=page_id,
                snippet=snippet,
                date=date,
                order=int(order) if isinstance(order, int) else 0,
                notebook_title=notebook_title,
                project_root=project_root,
            )
        )

    def _sort_key(occ: PersonOccurrence) -> tuple[Any, ...]:
        ref = refs.get(occ.page_id) if occ.page_id else None
        d = occ.date or (ref.date if ref else None)
        date_key = d.sort_key() if d else (9999, 99, 99)
        page_ord = ref.page_index if ref else 9999
        return (*date_key, page_ord, occ.order, occ.surface.casefold())

    return {
        key: sorted(items, key=_sort_key)
        for key, items in grouped.items()
    }


def build_notebook_page_refs(project_root: Path) -> dict[str, PageRef]:
    """Load page text and numbering for snippet context in the People panel."""
    from transcribe.ports import SystemClock, UuidGenerator
    from transcribe.services.project import ProjectService

    paths = open_project_paths(Path(project_root))
    svc = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
    try:
        project = svc.load(reconcile=False)
    except Exception:  # noqa: BLE001
        return {}
    count = len(project.pages)
    out: dict[str, PageRef] = {}
    for index, page in enumerate(project.pages):
        result = svc.load_page_result(page.page_id)
        text = (result.effective_text() if result else None) or ""
        out[page.page_id] = PageRef(
            page_index=index + 1,
            page_count=count,
            date=page.date,
            text=text,
        )
    return out


def load_notebook_person_occurrences(project_root: Path) -> dict[str, list[PersonOccurrence]]:
    """PERSON hits for one notebook with search-style snippets."""
    paths = open_project_paths(Path(project_root))
    storage = AnalysisStorage(paths)
    published = storage.read_published("ner")
    if published is None or published.get("outcome") != "success":
        return {}

    title = paths.root.name
    try:
        manifest = read_json(paths.manifest)
        if isinstance(manifest, dict) and isinstance(manifest.get("title"), str):
            title = manifest["title"].strip() or title
    except Exception:  # noqa: BLE001
        pass

    payload = published.get("payload") or {}
    evidence = published.get("evidence")
    page_refs = build_notebook_page_refs(Path(project_root))
    return extract_person_occurrences(
        payload if isinstance(payload, dict) else {},
        evidence=evidence if isinstance(evidence, list) else None,
        notebook_title=title,
        project_root=Path(project_root),
        page_refs=page_refs,
    )


def load_corpus_person_occurrences(projects_dir: Path) -> dict[str, list[PersonOccurrence]]:
    """Aggregate PERSON hits across notebooks."""
    merged: dict[str, list[PersonOccurrence]] = defaultdict(list)
    for root in discover_project_roots(Path(projects_dir)):
        for key, items in load_notebook_person_occurrences(root).items():
            merged[key].extend(items)
    for key in merged:
        merged[key].sort(
            key=lambda occ: (
                *(occ.date.sort_key() if occ.date else (9999, 99, 99)),
                occ.notebook_title or "",
                occ.order,
                occ.surface.casefold(),
            )
        )
    return dict(merged)
