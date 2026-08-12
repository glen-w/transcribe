"""Streamlit UI for notebook and corpus place maps (NER GPE/LOC/FAC)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.analysis.health import ModuleHealth
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.places import (
    GeocodeCache,
    GeocodedPlace,
    PlacesSnapshot,
    load_corpus_places,
    load_notebook_places,
    map_points,
    resolve_places,
    write_ner_locations_artifact,
)
from transcribe.ui.analysis_health_view import (
    module_may_show_payload,
    render_module_unavailable,
)


def _geocode_opt_in_key(scope: str) -> str:
    return f"places_geocode_allow_{scope}"


def _render_place_table(geocoded: list[GeocodedPlace], *, show_notebook: bool) -> None:
    if not geocoded:
        st.caption("No place entities (GPE / LOC / FAC) in published NER.")
        return
    rows: list[dict[str, Any]] = []
    for g in geocoded:
        row: dict[str, Any] = {
            "place": g.surface,
            "label": g.label,
            "mentions": g.count,
            "status": g.status,
            "resolved": g.display_name or "",
        }
        if show_notebook:
            row["notebook"] = g.notebook_title or ""
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_map(geocoded: list[GeocodedPlace]) -> None:
    points = map_points(geocoded)
    if not points:
        unresolved = sum(1 for g in geocoded if g.status != "ok")
        if unresolved:
            st.info(
                "No mapped coordinates yet. Enable OpenStreetMap geocoding below "
                "(place names leave this machine only when that option is on), "
                "or wait until cached results are available."
            )
        return
    st.map(points, latitude="lat", longitude="lon", size=40)
    st.caption(f"{len(points)} place(s) with coordinates · OpenStreetMap / Nominatim")


def _render_people(snapshot: PlacesSnapshot) -> None:
    if not snapshot.people:
        return
    st.markdown("#### People")
    top = snapshot.people[:30]
    lines = [f"- **{p.surface}** ×{p.count}" for p in top]
    st.markdown("\n".join(lines))


def render_places_panel(
    snapshot: PlacesSnapshot,
    *,
    runtime: RuntimePaths,
    scope: str,
    show_notebook: bool = False,
    ner_health: ModuleHealth | None = None,
    project_root: Path | None = None,
) -> None:
    """Shared panel: people list, place table, optional geocode + map."""
    if ner_health is not None:
        # Stale published NER may still power the map; only hard-stop when
        # there is no validated envelope at all.
        if ner_health.freshness == "unavailable" or ner_health.envelope is None:
            render_module_unavailable(ner_health, product_title="People & places")
            return
        if not module_may_show_payload(ner_health) and ner_health.freshness == "stale":
            st.caption("Named-entity results are out of date — map may reflect older text.")

    if not snapshot.ner_available:
        st.info(
            "No published NER result yet. Run Analyse (include **ner**) to extract "
            "places, then return here."
        )
        return

    if snapshot.ner_outcome and snapshot.ner_outcome != "success":
        st.warning(
            f"Published NER outcome is `{snapshot.ner_outcome}` — places map needs a "
            "successful run (spaCy optional extra)."
        )
        return

    if show_notebook:
        st.caption(
            f"Scanned {snapshot.notebooks_scanned} notebook(s); "
            f"{snapshot.notebooks_with_ner} with successful NER."
        )

    _render_people(snapshot)

    st.markdown("#### Places map")
    allow = st.checkbox(
        "Allow OpenStreetMap Nominatim geocoding (place names leave this machine)",
        value=bool(st.session_state.get(_geocode_opt_in_key(scope), False)),
        key=_geocode_opt_in_key(scope),
        help=(
            "Cached lookups stay local. New names are resolved via "
            "nominatim.openstreetmap.org only when this is checked "
            "(TranscriptX defaults geocoding on; Transcribe keeps it opt-in)."
        ),
    )

    cache = GeocodeCache(runtime)
    geocoded = resolve_places(
        snapshot.places,
        cache,
        allow_network=bool(allow),
    )
    # TX always writes ner-locations beside NER; persist when we have coords.
    if project_root is not None and any(g.status == "ok" for g in geocoded):
        nb_id = next((p.notebook_id for p in snapshot.places if p.notebook_id), None)
        nb_title = next(
            (p.notebook_title for p in snapshot.places if p.notebook_title), None
        )
        written = write_ner_locations_artifact(
            project_root,
            geocoded,
            notebook_id=nb_id,
            notebook_title=nb_title,
        )
        if written is not None:
            st.caption(f"Locations artifact: `{written.name}` under analysis/ner/")

    _render_map(geocoded)
    st.markdown("#### Place mentions")
    _render_place_table(geocoded, show_notebook=show_notebook)

    ok_n = sum(1 for g in geocoded if g.status == "ok")
    skipped_n = sum(1 for g in geocoded if g.status == "skipped")
    missing_n = sum(1 for g in geocoded if g.status == "not_found")
    st.caption(
        f"Resolved {ok_n}/{len(geocoded)} · skipped {skipped_n} · not found {missing_n}"
    )


def render_notebook_places_tab(
    *,
    project_root: Path,
    runtime: RuntimePaths,
    ner_health: ModuleHealth | None = None,
) -> None:
    st.subheader("People & places")
    st.caption(
        "Places and people from published NER (spaCy labels GPE / LOC / FAC / PERSON). "
        "The map geocodes place names with an optional OpenStreetMap lookup and a "
        "local cache. Run analysis from the preset form above if NER is missing."
    )
    snapshot = load_notebook_places(Path(project_root))
    render_places_panel(
        snapshot,
        runtime=runtime,
        scope="notebook",
        show_notebook=False,
        ner_health=ner_health,
        project_root=Path(project_root),
    )


def render_corpus_places_page(runtime: RuntimePaths) -> None:
    """Notebooks → Places: map of places mentioned across all notebooks."""
    st.caption(
        "Aggregates GPE / LOC / FAC entities from every notebook with a published "
        "NER result. Geocoding is optional and cached under the workspace data dir."
    )
    snapshot = load_corpus_places(runtime.projects_dir)
    if snapshot.notebooks_scanned == 0:
        st.info("No notebooks found yet. Create one under Workflow → New notebook.")
        return
    render_places_panel(
        snapshot,
        runtime=runtime,
        scope="corpus",
        show_notebook=True,
        ner_health=None,
    )
