"""Streamlit UI for notebook and corpus place maps (NER GPE/LOC/FAC)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from transcribe.analysis.health import ModuleHealth
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.places import (
    GeocodeCache,
    GeocodedPlace,
    PageRef,
    PersonOccurrence,
    PlacesSnapshot,
    build_notebook_page_refs,
    load_corpus_person_occurrences,
    load_corpus_places,
    load_notebook_person_occurrences,
    load_notebook_places,
    map_points,
    normalize_place_query,
    resolve_places,
    write_ner_locations_artifact,
)
from transcribe.ui import icons as ic
from transcribe.ui.analysis_health_view import (
    module_may_show_payload,
    render_module_unavailable,
)

SCOPE_NOTEBOOK = "notebook"
SCOPE_CORPUS = "corpus"
SCOPE_OPTIONS = (SCOPE_NOTEBOOK, SCOPE_CORPUS)
SCOPE_LABELS = {
    SCOPE_NOTEBOOK: "This notebook",
    SCOPE_CORPUS: "All notebooks",
}
PLACES_SCOPE_KEY = "places_ner_scope"


def _geocode_opt_in_key(scope: str) -> str:
    return f"places_geocode_allow_{scope}"


def render_places_scope_control(*, allow_notebook: bool = True) -> str:
    """This notebook | All notebooks toggle shared by People and Places panels."""
    options = list(SCOPE_OPTIONS) if allow_notebook else [SCOPE_CORPUS]
    current = st.session_state.get(PLACES_SCOPE_KEY, SCOPE_NOTEBOOK)
    if current not in options:
        current = options[0]
        st.session_state[PLACES_SCOPE_KEY] = current
    if len(options) == 1:
        st.session_state[PLACES_SCOPE_KEY] = options[0]
        st.caption(SCOPE_LABELS[options[0]])
        return options[0]
    chosen = st.segmented_control(
        "Scope",
        options=options,
        format_func=lambda s: SCOPE_LABELS[s],
        key=PLACES_SCOPE_KEY,
        help=(
            "This notebook: people and places from the open notebook’s published NER. "
            "All notebooks: aggregate every notebook with published NER."
        ),
        required=True,
        width="stretch",
    )
    if chosen is None:
        return current
    return str(chosen)

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
    st.dataframe(rows, width="stretch", hide_index=True)


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


def _render_people(
    snapshot: PlacesSnapshot,
    *,
    occurrences_by_person: dict[str, list[PersonOccurrence]],
    page_refs: dict[str, PageRef],
    show_notebook: bool,
    scope: str,
    on_occurrence_jump: Callable[[PersonOccurrence], None] | None = None,
) -> None:
    if not snapshot.people:
        st.caption("No people (PERSON) in published NER.")
        return
    top = snapshot.people[:30]
    for person in top:
        key = normalize_place_query(person.surface)
        occurrences = occurrences_by_person.get(key, [])
        with st.expander(f"{person.surface} ×{person.count}"):
            if not occurrences:
                st.caption("No page-level detail available.")
                continue
            for index, occ in enumerate(occurrences[:50]):
                cols = st.columns([3, 1])
                ref = page_refs.get(occ.page_id) if occ.page_id else None
                date_s = occ.date.format_display() if occ.date else "Undated"
                page_part = ""
                if ref:
                    page_part = f"p.{ref.page_index}/{ref.page_count} · "
                elif occ.page_id:
                    page_part = f"{occ.page_id} · "
                header_parts: list[str] = []
                if show_notebook and occ.notebook_title:
                    header_parts.append(f"**{escape_markdown_plain(occ.notebook_title)}**")
                header_parts.append(f"{page_part}{date_s}")
                cols[0].markdown(" · ".join(header_parts))
                if occ.snippet:
                    cols[0].caption(escape_markdown_plain(occ.snippet))
                if on_occurrence_jump and occ.page_id and cols[1].button(
                    "Jump to page",
                    key=f"people_jump_{scope}_{key}_{occ.page_id}_{index}",
                    type="tertiary",
                    icon=ic.ARROW_FORWARD,
                ):
                    on_occurrence_jump(occ)


def _ner_panel_blocked(
    snapshot: PlacesSnapshot,
    *,
    ner_health: ModuleHealth | None,
    product_title: str,
) -> bool:
    """Return True when the panel should stop (health gate or missing NER)."""
    if ner_health is not None:
        if ner_health.freshness == "unavailable" or ner_health.envelope is None:
            render_module_unavailable(ner_health, product_title=product_title)
            return True
        if not module_may_show_payload(ner_health) and ner_health.freshness == "stale":
            st.caption("Named-entity results are out of date — results may reflect older text.")

    if not snapshot.ner_available:
        st.info(
            "No published NER result yet. Run Analyse (include **ner**) to extract "
            "entities, then return here."
        )
        return True

    if snapshot.ner_outcome and snapshot.ner_outcome != "success":
        st.warning(
            f"Published NER outcome is `{snapshot.ner_outcome}` — NER needs a "
            "successful run (spaCy optional extra)."
        )
        return True
    return False


def render_people_panel(
    snapshot: PlacesSnapshot,
    *,
    ner_health: ModuleHealth | None = None,
    occurrences_by_person: dict[str, list[PersonOccurrence]] | None = None,
    page_refs: dict[str, PageRef] | None = None,
    show_notebook: bool = False,
    scope: str = "notebook",
    on_occurrence_jump: Callable[[PersonOccurrence], None] | None = None,
) -> None:
    """People list from published NER."""
    if _ner_panel_blocked(snapshot, ner_health=ner_health, product_title="People"):
        return
    _render_people(
        snapshot,
        occurrences_by_person=occurrences_by_person or {},
        page_refs=page_refs or {},
        show_notebook=show_notebook,
        scope=scope,
        on_occurrence_jump=on_occurrence_jump,
    )


def render_places_map_panel(
    snapshot: PlacesSnapshot,
    *,
    runtime: RuntimePaths,
    scope: str,
    show_notebook: bool = False,
    ner_health: ModuleHealth | None = None,
    project_root: Path | None = None,
) -> None:
    """Place map, geocode opt-in, and mention table from published NER."""
    if _ner_panel_blocked(snapshot, ner_health=ner_health, product_title="Places"):
        return

    if show_notebook:
        st.caption(
            f"Scanned {snapshot.notebooks_scanned} notebook(s); "
            f"{snapshot.notebooks_with_ner} with successful NER."
        )

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
    if project_root is not None and any(g.status == "ok" for g in geocoded):
        nb_id = next((p.notebook_id for p in snapshot.places if p.notebook_id), None)
        nb_title = next((p.notebook_title for p in snapshot.places if p.notebook_title), None)
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
    st.caption(f"Resolved {ok_n}/{len(geocoded)} · skipped {skipped_n} · not found {missing_n}")


def _render_entity_sentiment(
    entity_sentiment_health: ModuleHealth,
    *,
    show_advanced: bool,
) -> None:
    from transcribe.ui.analysis_health_view import (
        render_advanced_payload,
        render_module_unavailable,
    )
    from transcribe.ui.analysis_product_views import render_entity_sentiment_section

    if not module_may_show_payload(entity_sentiment_health):
        if entity_sentiment_health.envelope is not None:
            render_module_unavailable(entity_sentiment_health, product_title="Entity tone")
        return
    env = entity_sentiment_health.envelope or {}
    payload = env.get("payload") if isinstance(env, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    outcome = env.get("outcome") if isinstance(env, dict) else None
    if outcome in {"failed", "insufficient_data", "skipped_not_applicable"}:
        render_module_unavailable(entity_sentiment_health, product_title="Entity tone")
        return
    st.divider()
    render_entity_sentiment_section(payload)
    if show_advanced:
        render_advanced_payload("entity_sentiment", payload)


def render_notebook_people_tab(
    *,
    project_root: Path | None,
    runtime: RuntimePaths,
    scope: str = SCOPE_NOTEBOOK,
    ner_health: ModuleHealth | None = None,
    entity_sentiment_health: ModuleHealth | None = None,
    show_advanced: bool = False,
    heading: bool = True,
    on_occurrence_jump: Callable[[PersonOccurrence], None] | None = None,
) -> None:
    if heading:
        st.subheader("People")
    corpus = scope == SCOPE_CORPUS or project_root is None
    if corpus:
        st.caption(
            "People (spaCy PERSON) aggregated from every notebook with published NER. "
            "Jump opens the mention’s notebook in Reading."
        )
        snapshot = load_corpus_places(runtime.projects_dir)
        if snapshot.notebooks_scanned == 0:
            st.info("No notebooks found yet. Create one under Workflow → New notebook.")
            return
        occurrences = load_corpus_person_occurrences(runtime.projects_dir)
        page_refs: dict[str, PageRef] = {}
        roots = {
            occ.project_root
            for items in occurrences.values()
            for occ in items
            if occ.project_root is not None
        }
        for root in roots:
            page_refs.update(build_notebook_page_refs(root))
        render_people_panel(
            snapshot,
            ner_health=None,
            occurrences_by_person=occurrences,
            page_refs=page_refs,
            show_notebook=True,
            scope=SCOPE_CORPUS,
            on_occurrence_jump=on_occurrence_jump,
        )
        return

    st.caption(
        "People from published NER (spaCy label PERSON). Entity tone joins NER surfaces "
        "to page sentiment when that module has been published. Run Analyse from "
        "Workflow → Analyse if NER is missing."
    )
    root = Path(project_root)
    snapshot = load_notebook_places(root)
    page_refs = build_notebook_page_refs(root)
    occurrences = load_notebook_person_occurrences(root)
    render_people_panel(
        snapshot,
        ner_health=ner_health,
        occurrences_by_person=occurrences,
        page_refs=page_refs,
        scope=SCOPE_NOTEBOOK,
        on_occurrence_jump=on_occurrence_jump,
    )
    if entity_sentiment_health is not None:
        _render_entity_sentiment(entity_sentiment_health, show_advanced=show_advanced)


def render_notebook_places_tab(
    *,
    project_root: Path | None,
    runtime: RuntimePaths,
    scope: str = SCOPE_NOTEBOOK,
    ner_health: ModuleHealth | None = None,
    show_advanced: bool = False,
    heading: bool = True,
) -> None:
    if heading:
        st.subheader("Places")
    _ = show_advanced
    corpus = scope == SCOPE_CORPUS or project_root is None
    if corpus:
        st.caption(
            "Places (GPE / LOC / FAC) from every notebook with published NER. "
            "Geocoding is optional and cached under the workspace data dir."
        )
        snapshot = load_corpus_places(runtime.projects_dir)
        if snapshot.notebooks_scanned == 0:
            st.info("No notebooks found yet. Create one under Workflow → New notebook.")
            return
        render_places_map_panel(
            snapshot,
            runtime=runtime,
            scope=SCOPE_CORPUS,
            show_notebook=True,
            ner_health=None,
        )
        return

    st.caption(
        "Places from published NER (spaCy labels GPE / LOC / FAC). The map geocodes "
        "place names with an optional OpenStreetMap lookup and a local cache. "
        "Run Analyse from Workflow → Analyse if NER is missing."
    )
    root = Path(project_root)
    snapshot = load_notebook_places(root)
    render_places_map_panel(
        snapshot,
        runtime=runtime,
        scope=SCOPE_NOTEBOOK,
        show_notebook=False,
        ner_health=ner_health,
        project_root=root,
    )


def render_corpus_places_page(runtime: RuntimePaths) -> None:
    """Places: map of places mentioned across all notebooks (no notebook selected)."""
    render_notebook_places_tab(
        project_root=None,
        runtime=runtime,
        scope=SCOPE_CORPUS,
        heading=False,
    )
