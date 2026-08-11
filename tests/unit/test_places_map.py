"""Places extraction and geocode cache (offline; mocked network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.runtime_paths import RuntimePaths
from transcribe.services.places import (
    GeocodeCache,
    PlaceMention,
    extract_from_ner_payload,
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
    snap = extract_from_ner_payload(
        payload, notebook_id="nb1", notebook_title="Travel"
    )
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

    resolved = resolve_places(
        places, cache, allow_network=False, geocode_fn=boom
    )
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
    shell = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    assert '"Places"' in shell
    app = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
    assert "People & places" in app
    assert "render_corpus_places_page" in app
    assert "render_notebook_places_tab" in app


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
    places = [
        PlaceMention(surface=f"City{i}", label="GPE", count=1) for i in range(3)
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
    assert len(calls) == 1
    assert resolved[0].status == "ok"
    assert resolved[1].status == "pending"
    assert resolved[2].status == "pending"


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
