"""Places from NER: extract GPE/LOC/FAC, optional Nominatim geocode + local cache.

Maps are a read-model over published ``ner`` payloads — not a new analysis module.
Network geocoding is opt-in; cached coordinates work fully offline.
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
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import FileLock
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import discover_project_roots
from transcribe.services.project import open_project_paths

PLACE_LABELS = frozenset({"GPE", "LOC", "FAC"})
PERSON_LABEL = "PERSON"

GEOCODE_CACHE_SCHEMA = "transcribe.geocode-cache"
GEOCODE_CACHE_VERSION = 1
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "TranscribeNotebookOCR/0.2 (local-first; places map; contact: local)"
_MIN_REQUEST_INTERVAL_S = 1.05
_DEFAULT_TIMEOUT_S = 12.0

_WS_RE = re.compile(r"\s+")


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


@dataclass(frozen=True)
class PersonMention:
    surface: str
    count: int
    page_ids: tuple[str, ...] = ()


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
        # Analysis units often use page_id as unit_id for page-grained docs.
        return unit_id
    return None


def extract_from_ner_payload(
    payload: dict[str, Any] | None,
    *,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> PlacesSnapshot:
    """Aggregate place/person surfaces from a published ``ner_payload_v1``."""
    if not isinstance(payload, dict):
        return PlacesSnapshot(ner_available=False)

    entities = payload.get("entities")
    if not isinstance(entities, list):
        # Fall back to entity_counts when detailed rows are missing.
        counts = payload.get("entity_counts") or {}
        places: list[PlaceMention] = []
        if isinstance(counts, dict):
            # Without labels we cannot safely map — treat as empty places.
            _ = counts
        return PlacesSnapshot(
            places=places,
            ner_available=True,
            ner_outcome="success",
            notebooks_scanned=1 if notebook_id else 0,
            notebooks_with_ner=1 if notebook_id else 0,
        )

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
                    "notebook_titles": {p.notebook_title} if p.notebook_title else set(),
                }
            else:
                slot["count"] += p.count
                slot["page_ids"].update(p.page_ids)
                if p.notebook_id:
                    slot["notebook_ids"].add(p.notebook_id)
                if p.notebook_title:
                    slot["notebook_titles"].add(p.notebook_title)
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
            )
        )
    people = [
        PersonMention(
            surface=slot["surface"],
            count=int(slot["count"]),
            page_ids=tuple(sorted(slot["page_ids"])),
        )
        for _k, slot in sorted(
            person_merge.items(), key=lambda kv: (-kv[1]["count"], kv[0])
        )
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
    snap = extract_from_ner_payload(
        payload if isinstance(payload, dict) else {},
        notebook_id=notebook_id,
        notebook_title=title,
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
    """Workspace-scoped durable geocode cache under ``data/cache/geocode.json``."""

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
    """Resolve a place name via OpenStreetMap Nominatim (network)."""
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


def resolve_places(
    places: list[PlaceMention],
    cache: GeocodeCache,
    *,
    allow_network: bool = False,
    geocode_fn: GeocodeFn | None = None,
    max_network_lookups: int = 40,
    sleep_fn: Callable[[float], None] | None = None,
) -> list[GeocodedPlace]:
    """Attach coordinates using cache first, then optional network geocoding."""
    geocode = geocode_fn or nominatim_geocode
    sleeper = sleep_fn or time.sleep
    out: list[GeocodedPlace] = []
    network_used = 0
    last_network_at = 0.0

    for place in places:
        query = place.surface.strip()
        cached = cache.get(query)
        if cached and cached.get("status") in {"ok", "not_found"}:
            out.append(
                GeocodedPlace(
                    surface=place.surface,
                    query=query,
                    lat=cached.get("lat"),
                    lon=cached.get("lon"),
                    display_name=cached.get("display_name"),
                    status=str(cached.get("status")),
                    label=place.label,
                    count=place.count,
                    page_ids=place.page_ids,
                    notebook_id=place.notebook_id,
                    notebook_title=place.notebook_title,
                    provider=cached.get("provider"),
                    message=cached.get("message"),
                )
            )
            continue

        if not allow_network or network_used >= max_network_lookups:
            out.append(
                GeocodedPlace(
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
                )
            )
            continue

        # Nominatim usage policy: ≤1 req/s
        elapsed = time.monotonic() - last_network_at
        if last_network_at and elapsed < _MIN_REQUEST_INTERVAL_S:
            sleeper(_MIN_REQUEST_INTERVAL_S - elapsed)

        result = geocode(query)
        last_network_at = time.monotonic()
        network_used += 1
        entry = {
            "status": result.get("status") or "error",
            "lat": result.get("lat"),
            "lon": result.get("lon"),
            "display_name": result.get("display_name"),
            "provider": result.get("provider") or "nominatim",
            "message": result.get("message"),
            "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if entry["status"] in {"ok", "not_found"}:
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
            )
        )
    return out


def map_points(geocoded: list[GeocodedPlace]) -> list[dict[str, Any]]:
    """Rows suitable for ``st.map`` (lat/lon) plus tooltip metadata."""
    rows: list[dict[str, Any]] = []
    for g in geocoded:
        if g.status != "ok" or g.lat is None or g.lon is None:
            continue
        rows.append(
            {
                "lat": float(g.lat),
                "lon": float(g.lon),
                "surface": g.surface,
                "label": g.label,
                "count": g.count,
                "display_name": g.display_name or g.surface,
                "notebook": g.notebook_title or "",
            }
        )
    return rows


# Re-export ProjectPaths typing helper for callers that already have paths open.
def load_notebook_places_from_paths(paths: ProjectPaths) -> PlacesSnapshot:
    return load_notebook_places(paths.root)
