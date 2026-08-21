"""Places extraction and geocode cache (offline; mocked network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.runtime_paths import RuntimePaths
from transcribe.services.places import (
    GeocodeCache,
    PageRef,
    PersonOccurrence,
    PlaceMention,
    extract_from_ner_payload,
    extract_person_occurrences,
    load_corpus_places,
    load_notebook_places,
    map_points,
    normalize_place_query,
    resolve_places,
)


def test_normalize_place_query_collapses_case_and_space() -> None:
    assert normalize_place_query("  New   York ") == "new york"
    assert normalize_place_query("PARIS") == "paris"


def test_extract_places_and_people_from_ner_payload() -> None:
    payload = {
        "schema": "ner_payload_v1",
        "entities": [
            {
                "surface": "Paris",
                "label": "GPE",
                "unit_id": "p1",
                "source_ref": {"kind": "page", "page_id": "p1"},
            },
            {"surface": "Paris", "label": "GPE", "unit_id": "p2"},
            {"surface": "Seine", "label": "LOC", "unit_id": "p1"},
            {"surface": "Alice", "label": "PERSON", "unit_id": "p1"},
            {"surface": "Monday", "label": "DATE", "unit_id": "p1"},
        ],
    }
    snap = extract_from_ner_payload(payload, notebook_id="nb1", notebook_title="Travel")
    assert snap.ner_available
    assert [p.surface for p in snap.places] == ["Paris", "Seine"]
    paris = snap.places[0]
    assert paris.label == "GPE"
    assert paris.count == 2
    assert set(paris.page_ids) == {"p1", "p2"}
    assert paris.notebook_title == "Travel"
    assert snap.people[0].surface == "Alice"
    assert snap.people[0].count == 1


def test_resolve_places_uses_cache_without_network(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    cache.put(
        "Paris",
        {
            "status": "ok",
            "lat": 48.8566,
            "lon": 2.3522,
            "display_name": "Paris, France",
            "provider": "cache-test",
        },
    )
    places = [
        PlaceMention(surface="Paris", label="GPE", count=3),
        PlaceMention(surface="Atlantis", label="GPE", count=1),
    ]
    calls: list[str] = []

    def boom(q: str) -> dict:
        calls.append(q)
        raise AssertionError("network should not be called")

    resolved = resolve_places(places, cache, allow_network=False, geocode_fn=boom)
    assert calls == []
    assert resolved[0].status == "ok"
    assert resolved[0].lat == pytest.approx(48.8566)
    assert resolved[1].status == "skipped"
    points = map_points(resolved)
    assert len(points) == 1
    assert points[0]["surface"] == "Paris"


def test_resolve_places_network_opt_in_and_cache_write(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    places = [PlaceMention(surface="Lyon", label="GPE", count=1)]

    def fake_geocode(q: str) -> dict:
        assert q == "Lyon"
        return {
            "status": "ok",
            "lat": 45.75,
            "lon": 4.85,
            "display_name": "Lyon, France",
            "provider": "nominatim",
        }

    resolved = resolve_places(
        places,
        cache,
        allow_network=True,
        geocode_fn=fake_geocode,
        sleep_fn=lambda _s: None,
    )
    assert resolved[0].status == "ok"
    assert resolved[0].lat == pytest.approx(45.75)
    cached = cache.get("Lyon")
    assert cached is not None
    assert cached["status"] == "ok"
    assert cached["lat"] == pytest.approx(45.75)


def test_load_notebook_and_corpus_places(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    nb_a = projects / "a"
    nb_b = projects / "b"
    for nb, title, ents in (
        (
            nb_a,
            "A",
            [
                {
                    "surface": "Paris",
                    "label": "GPE",
                    "unit_id": "p1",
                    "source_ref": {"page_id": "p1"},
                }
            ],
        ),
        (
            nb_b,
            "B",
            [
                {
                    "surface": "Paris",
                    "label": "GPE",
                    "unit_id": "p9",
                    "source_ref": {"page_id": "p9"},
                },
                {"surface": "Berlin", "label": "GPE", "unit_id": "p9"},
            ],
        ),
    ):
        (nb / "analysis" / "ner").mkdir(parents=True)
        (nb / "project.json").write_text(
            json.dumps(
                {
                    "format": "transcribe.project",
                    "schema_version": 1,
                    "id": nb.name,
                    "title": title,
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": "2020-01-01T00:00:00Z",
                    "settings": {},
                    "sources": [],
                    "pages": [],
                    "renders": {},
                }
            ),
            encoding="utf-8",
        )
        (nb / "analysis" / "ner" / "published.json").write_text(
            json.dumps(
                {
                    "format": "transcribe.analysis-result",
                    "schema_version": 1,
                    "module_id": "ner",
                    "outcome": "success",
                    "payload": {"schema": "ner_payload_v1", "entities": ents},
                }
            ),
            encoding="utf-8",
        )

    one = load_notebook_places(nb_a)
    assert one.notebooks_with_ner == 1
    assert [p.surface for p in one.places] == ["Paris"]

    corpus = load_corpus_places(projects)
    assert corpus.notebooks_scanned == 2
    assert corpus.notebooks_with_ner == 2
    by_name = {p.surface: p for p in corpus.places}
    assert by_name["Paris"].count == 2
    assert by_name["Berlin"].count == 1


def test_shell_and_app_wire_places_surfaces() -> None:
    nav = Path("src/transcribe/ui/navigation.py").read_text(encoding="utf-8")
    assert 'id="Places"' in nav
    assert 'nav_label="People & Places"' in nav
    assert 'section="view"' in nav
    app = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
    views = Path("src/transcribe/ui/notebook_views.py").read_text(encoding="utf-8")
    assert "People" in nav
    assert '"places"' in nav
    assert '"corpus"' not in nav.split("VIEW_PAGE_PANELS")[1].split("_VIEW_PANEL_ALIASES")[0]
    assert "render_view_places" in app
    assert "render_places_without_notebook" in app
    assert "render_view_places" in views
    assert "render_places_scope_control" in views
    assert "render_notebook_people_tab" in views
    assert "render_notebook_places_tab" in views
    places_map = Path("src/transcribe/ui/places_map.py").read_text(encoding="utf-8")
    assert "render_places_scope_control" in places_map
    assert "load_corpus_person_occurrences" in places_map
    assert "This notebook" in places_map
    assert "All notebooks" in places_map
    assert "st.expander" in places_map
    assert "Jump to page" in places_map


def test_places_service_has_no_streamlit_import() -> None:
    source = Path("src/transcribe/services/places.py").read_text(encoding="utf-8")
    assert "streamlit" not in source


def test_nominatim_geocode_parses_mock_response() -> None:
    from io import BytesIO
    from transcribe.services.places import nominatim_geocode

    class _Resp(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payload = b'[{"lat":"51.5","lon":"-0.12","display_name":"London, UK"}]'

    def opener(req, timeout=12.0):
        assert "nominatim.openstreetmap.org" in req.full_url
        assert req.get_header("User-agent") or req.headers.get("User-agent")
        return _Resp(payload)

    result = nominatim_geocode("London", opener=opener)
    assert result["status"] == "ok"
    assert result["lat"] == pytest.approx(51.5)
    assert result["lon"] == pytest.approx(-0.12)
    assert "London" in (result["display_name"] or "")


def test_nominatim_geocode_empty_list_is_not_found() -> None:
    from io import BytesIO
    from transcribe.services.places import nominatim_geocode

    class _Resp(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(req, timeout=12.0):
        return _Resp(b"[]")

    result = nominatim_geocode("NowherevilleXYZ", opener=opener)
    assert result["status"] == "not_found"


def test_resolve_places_respects_lookup_budget(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    # Frequency-rank: City2 (count=9) should be the only live lookup when budget=1.
    places = [
        PlaceMention(surface="City0", label="GPE", count=1),
        PlaceMention(surface="City1", label="GPE", count=2),
        PlaceMention(surface="City2", label="GPE", count=9),
    ]
    calls: list[str] = []

    def fake(q: str) -> dict:
        calls.append(q)
        return {
            "status": "ok",
            "lat": 1.0 + len(calls),
            "lon": 2.0,
            "display_name": q,
            "provider": "fake",
        }

    resolved = resolve_places(
        places,
        cache,
        allow_network=True,
        geocode_fn=fake,
        max_network_lookups=1,
        sleep_fn=lambda _s: None,
    )
    assert calls == ["City2"]
    by_name = {r.surface: r for r in resolved}
    assert by_name["City2"].status == "ok"
    assert by_name["City0"].status == "pending"
    assert by_name["City1"].status == "pending"


def test_resolve_places_caches_errors(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    places = [PlaceMention(surface="Flaky", label="GPE", count=1)]
    calls = {"n": 0}

    def flaky(q: str) -> dict:
        calls["n"] += 1
        return {
            "status": "error",
            "lat": None,
            "lon": None,
            "message": "timeout",
            "provider": "fake",
        }

    first = resolve_places(
        places, cache, allow_network=True, geocode_fn=flaky, sleep_fn=lambda _s: None
    )
    assert first[0].status == "error"
    assert calls["n"] == 1

    second = resolve_places(
        places,
        cache,
        allow_network=True,
        geocode_fn=lambda q: (_ for _ in ()).throw(AssertionError("no retry")),
        sleep_fn=lambda _s: None,
    )
    assert second[0].status == "error"
    assert calls["n"] == 1


def test_ner_locations_artifact_shape(tmp_path: Path) -> None:
    from transcribe.services.places import (
        GeocodedPlace,
        build_ner_locations_artifact,
        write_ner_locations_artifact,
    )

    geocoded = [
        GeocodedPlace(
            surface="Paris",
            query="Paris",
            lat=48.85,
            lon=2.35,
            display_name="Paris, France",
            status="ok",
            label="GPE",
            count=2,
            page_ids=("p1",),
            sample_quote="in Paris",
        ),
        GeocodedPlace(
            surface="Atlantis",
            query="Atlantis",
            lat=None,
            lon=None,
            display_name=None,
            status="not_found",
            label="GPE",
            count=1,
        ),
    ]
    payload = build_ner_locations_artifact(geocoded, notebook_id="nb1", notebook_title="Travel")
    assert payload["format"] == "transcribe.ner-locations"
    assert payload["schema_version"] == 1
    assert len(payload["places"]) == 1
    assert payload["places"][0]["name"] == "Paris"
    assert payload["places"][0]["sentence"] == "in Paris"
    assert payload["places"][0]["page_ids"] == ["p1"]

    nb = tmp_path / "proj"
    (nb / "analysis" / "ner").mkdir(parents=True)
    (nb / "project.json").write_text("{}", encoding="utf-8")
    path = write_ner_locations_artifact(nb, geocoded, notebook_id="nb1", notebook_title="Travel")
    assert path is not None
    assert path.name == "locations.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["places"][0]["lat"] == pytest.approx(48.85)


def test_place_labels_include_tx_parity_plus_fac() -> None:
    from transcribe.services.places import PLACE_LABELS, PLACE_LABELS_TX

    assert PLACE_LABELS_TX == frozenset({"GPE", "LOC"})
    assert "FAC" in PLACE_LABELS
    assert PLACE_LABELS_TX <= PLACE_LABELS


def test_extract_attaches_evidence_quote() -> None:
    snap = extract_from_ner_payload(
        {
            "entities": [
                {"surface": "Paris", "label": "GPE", "unit_id": "p1"},
            ]
        },
        evidence=[
            {"label": "GPE", "surface": "Paris", "quote": "visited Paris yesterday"},
        ],
    )
    assert snap.places[0].sample_quote == "visited Paris yesterday"


def test_resolve_places_caches_not_found(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    places = [PlaceMention(surface="Xyzzy", label="GPE", count=1)]

    def miss(q: str) -> dict:
        return {
            "status": "not_found",
            "lat": None,
            "lon": None,
            "display_name": None,
            "provider": "fake",
        }

    first = resolve_places(
        places, cache, allow_network=True, geocode_fn=miss, sleep_fn=lambda _s: None
    )
    assert first[0].status == "not_found"

    def boom(q: str) -> dict:
        raise AssertionError("should use cache")

    second = resolve_places(
        places, cache, allow_network=True, geocode_fn=boom, sleep_fn=lambda _s: None
    )
    assert second[0].status == "not_found"


def test_corrupt_ok_cache_without_coords_becomes_error(tmp_path: Path) -> None:
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    runtime.ensure_layout()
    cache = GeocodeCache(runtime)
    cache.put("Broken", {"status": "ok", "lat": None, "lon": None})
    resolved = resolve_places(
        [PlaceMention(surface="Broken", label="FAC", count=1)],
        cache,
        allow_network=False,
    )
    assert resolved[0].status == "error"
    assert map_points(resolved) == []


def test_extract_fac_label() -> None:
    snap = extract_from_ner_payload(
        {
            "entities": [
                {"surface": "Louvre", "label": "FAC", "unit_id": "p1"},
            ]
        }
    )
    assert snap.places[0].label == "FAC"
    assert snap.places[0].surface == "Louvre"


def test_extract_person_occurrences_with_snippet() -> None:
    payload = {
        "entities": [
            {
                "surface": "Alice",
                "label": "PERSON",
                "unit_id": "page-1",
                "order": 2,
                "char_start": 12,
                "char_end": 17,
                "date": {"y": 1999, "m": 3, "d": 4},
            },
            {
                "surface": "Alice",
                "label": "PERSON",
                "unit_id": "page-2",
                "order": 5,
                "char_start": 0,
                "char_end": 5,
            },
        ],
    }
    evidence = [
        {
            "unit_id": "page-1",
            "label": "PERSON",
            "char_start": 12,
            "char_end": 17,
            "quote": "Alice",
        },
    ]
    page_refs = {
        "page-1": PageRef(
            page_index=1,
            page_count=3,
            text="Yesterday I met Alice at the park and we talked for hours.",
        ),
        "page-2": PageRef(page_index=2, page_count=3, text="Alice called later that evening."),
    }
    grouped = extract_person_occurrences(
        payload,
        evidence=evidence,
        page_refs=page_refs,
        notebook_title="Diary",
    )
    alice_key = normalize_place_query("Alice")
    assert len(grouped[alice_key]) == 2
    first = grouped[alice_key][0]
    assert first.page_id == "page-1"
    assert first.date is not None
    assert first.date.year == 1999
    assert "Alice" in first.snippet
    assert "met" in first.snippet or "park" in first.snippet
    second = grouped[alice_key][1]
    assert second.page_id == "page-2"
    assert "Alice" in second.snippet


def test_load_notebook_without_ner(tmp_path: Path) -> None:
    nb = tmp_path / "empty"
    nb.mkdir()
    (nb / "project.json").write_text(
        json.dumps(
            {
                "format": "transcribe.project",
                "schema_version": 1,
                "id": "empty",
                "title": "Empty",
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2020-01-01T00:00:00Z",
                "settings": {},
                "sources": [],
                "pages": [],
                "renders": {},
            }
        ),
        encoding="utf-8",
    )
    snap = load_notebook_places(nb)
    assert snap.ner_available is False
    assert snap.places == []
    assert snap.notebooks_scanned == 1
