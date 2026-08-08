"""Archive, notebook browser, and search Streamlit views."""

from __future__ import annotations

import streamlit as st

from transcribe.domain.dates import ApproximateDate, bin_key_to_date
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import (
    ActivityBin,
    ArchiveFilters,
    ArchiveService,
    NotebookSummary,
    TimelineBin,
)
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.thumbnails import ThumbnailService
from transcribe.ui.page_viewer import open_page_context


def _filters_from_widgets(
    *,
    period: str,
    year: int | None,
    query: str,
    selected_media: list[str],
    selected_project_tags: list[str],
    selected_tags: list[str],
    include_undated: bool,
    range_start: ApproximateDate | None = None,
    range_end: ApproximateDate | None = None,
) -> ArchiveFilters:
    return ArchiveFilters(
        period=period if period in ("all", "year", "range") else "all",  # type: ignore[arg-type]
        year=year if period == "year" else None,
        range_start=range_start if period == "range" else None,
        range_end=range_end if period == "range" else None,
        query=query.strip(),
        media_types=tuple(selected_media),
        project_tags=tuple(selected_project_tags),
        tags=tuple(selected_tags),
        include_undated=include_undated,
    )


def _activity_chart(bins: list[TimelineBin] | list[ActivityBin], grain: str, *, height: int) -> None:
    if not bins:
        return
    try:
        import altair as alt
        import pandas as pd

        rows = [
            {"when": bin_key_to_date(b.key, grain), "pages": b.count, "label": b.key}
            for b in bins
        ]
        df = pd.DataFrame(rows)
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("when:T", title=None),
                y=alt.Y("pages:Q", title="Pages"),
                tooltip=["label", "pages"],
            )
            .properties(height=height)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.bar_chart(
            {"bin": [b.key for b in bins], "pages": [b.count for b in bins]},
            x="bin",
            y="pages",
            height=height,
        )


def render_archive(runtime: RuntimePaths, archive: ArchiveService) -> None:
    from transcribe.ui.page_viewer import _parse_date_input

    del runtime
    archive.ensure_index()
    st.subheader("Archive")
    years = archive.available_years()
    period_options = ["All", "Year", "Range"] if years else ["All", "Range"]
    period = st.selectbox("Period", period_options, index=0)
    year = None
    range_start = None
    range_end = None
    if period == "Year" and years:
        year = st.selectbox("Year", years, index=len(years) - 1)
        period_key = "year"
    elif period == "Range":
        period_key = "range"
        c1, c2 = st.columns(2)
        start_raw = c1.text_input("From (YYYY / YYYY-MM / YYYY-MM-DD)", value="")
        end_raw = c2.text_input("To (YYYY / YYYY-MM / YYYY-MM-DD)", value="")
        try:
            range_start = _parse_date_input(start_raw) if start_raw.strip() else None
            range_end = _parse_date_input(end_raw) if end_raw.strip() else None
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        period_key = "all"

    query = st.text_input("Search / filter term", value="", key="archive_query")
    include_undated = st.checkbox("Include undated pages in counts", value=True)
    tag_filter = st.text_input("Tag filter (comma-separated, AND)", "")
    selected_tags = [t.strip() for t in tag_filter.split(",") if t.strip()]

    # Type inventory with period/query/tags applied (types unconstrained) for selected/total.
    base_for_types = _filters_from_widgets(
        period=period_key,
        year=year,
        query=query,
        selected_media=[],
        selected_project_tags=[],
        selected_tags=selected_tags,
        include_undated=include_undated,
        range_start=range_start,
        range_end=range_end,
    )
    inventory = archive.type_inventory(base_for_types)
    media_keys = [t.key for t in inventory if t.kind == "media_type"]
    project_tag_keys = [t.key for t in inventory if t.kind == "project_tag"]

    selected_media: list[str] = []
    selected_project_tags: list[str] = []
    if media_keys or project_tag_keys:
        st.caption("Types (OR)")
        cols = st.columns(max(1, min(6, len(media_keys) + len(project_tag_keys))))
        i = 0
        for tc in inventory:
            if tc.kind == "media_type":
                label = f"{tc.key} ({tc.selected} of {tc.total})"
                key = f"arc_mt_{tc.key}"
                default_on = True
                bucket = selected_media
            else:
                label = f"{tc.key} ({tc.selected} of {tc.total})"
                key = f"arc_pt_{tc.key}"
                default_on = True
                bucket = selected_project_tags
            if cols[i % len(cols)].checkbox(label, value=default_on, key=key):
                bucket.append(tc.key)
            i += 1

    if selected_media and media_keys and set(selected_media) == set(media_keys):
        selected_media = []
    if (
        selected_project_tags
        and project_tag_keys
        and set(selected_project_tags) == set(project_tag_keys)
    ):
        selected_project_tags = []

    filters = _filters_from_widgets(
        period=period_key,
        year=year,
        query=query,
        selected_media=selected_media,
        selected_project_tags=selected_project_tags,
        selected_tags=selected_tags,
        include_undated=include_undated,
        range_start=range_start,
        range_end=range_end,
    )
    timeline = archive.timeline(filters)
    st.markdown(
        f"Showing **{timeline.showing}** of **{timeline.total}** pages"
        + (
            f" · {timeline.undated_count} undated (excluded from spikes)"
            if timeline.undated_count
            else ""
        )
    )

    if timeline.bins:
        _activity_chart(timeline.bins, timeline.grain, height=220)
        st.caption(f"Activity by {timeline.grain} (zeros preserve gaps)")
    else:
        st.info("No dated pages match the current filters.")

    notebooks = archive.list_notebooks(order="oldest", filters=filters)
    st.markdown("#### Notebooks")
    if not notebooks:
        st.caption("No notebooks match the current filters.")
        return

    show_n = int(st.session_state.get("archive_strip_n", 12))
    strip = notebooks[:show_n]
    cols = st.columns(min(6, max(1, len(strip))))
    for i, nb in enumerate(strip):
        with cols[i % len(cols)]:
            _notebook_card(nb, return_mode="Archive")
    if show_n < len(notebooks):
        if st.button(f"Show more notebooks ({len(notebooks) - show_n} remaining)"):
            st.session_state["archive_strip_n"] = show_n + 12
            st.rerun()
    elif show_n > 12:
        if st.button("Show fewer"):
            st.session_state["archive_strip_n"] = 12
            st.rerun()


def _notebook_card(nb: NotebookSummary, *, return_mode: str) -> None:
    paths = open_project_paths(nb.root)
    projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
    try:
        project = projects.load(reconcile=False)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"{nb.title}: {exc}")
        return
    thumbs = ThumbnailService(paths)
    cover_id = thumbs.cover_page_id(project)
    if cover_id:
        thumb = thumbs.ensure_thumb(project, cover_id)
        if thumb and thumb.exists():
            st.image(str(thumb), width="stretch")
    date_label = "Undated"
    if nb.date_start or nb.date_end:
        a = nb.date_start.format_display() if nb.date_start else "?"
        b = nb.date_end.format_display() if nb.date_end else "?"
        date_label = f"{a} → {b}"
    st.caption(nb.title)
    st.caption(date_label)
    rate = f"{nb.pages_per_day} pages/day" if nb.pages_per_day is not None else "rate n/a"
    st.caption(f"{nb.page_count} pages · {rate}")
    page_ids = [p.page_id for p in project.pages]
    open_id = cover_id or (page_ids[0] if page_ids else None)
    if open_id and st.button("Open", key=f"open_nb_{nb.project_id}_{return_mode}"):
        open_page_context(
            page_id=open_id,
            page_ids=page_ids,
            project_root=nb.root,
            return_mode=return_mode,
        )
        st.session_state["ui_mode"] = return_mode
        st.rerun()
    if st.button("Workflow", key=f"wf_nb_{nb.project_id}_{return_mode}"):
        st.session_state["root"] = str(nb.root)
        st.session_state["ui_mode"] = "Workflow"
        st.session_state["show_page_viewer"] = False
        st.rerun()


def render_notebooks(runtime: RuntimePaths, archive: ArchiveService) -> None:
    del runtime
    archive.ensure_index()
    st.subheader("Notebooks")
    order = st.selectbox(
        "Order",
        ["oldest", "newest", "most_pages"],
        format_func=lambda x: {
            "oldest": "Oldest first",
            "newest": "Newest first",
            "most_pages": "Most pages",
        }[x],
    )
    notebooks = archive.list_notebooks(order=order)  # type: ignore[arg-type]
    if not notebooks:
        st.info("No notebooks in the projects directory.")
        return
    for nb in notebooks:
        left, right = st.columns([1, 4])
        with left:
            paths = open_project_paths(nb.root)
            projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
            try:
                project = projects.load(reconcile=False)
            except Exception:
                project = None
            if project:
                thumbs = ThumbnailService(paths)
                cover_id = thumbs.cover_page_id(project)
                if cover_id:
                    thumb = thumbs.ensure_thumb(project, cover_id)
                    if thumb and thumb.exists():
                        st.image(str(thumb), width="stretch")
        with right:
            st.markdown(f"**{nb.title}**")
            if nb.date_start or nb.date_end:
                a = nb.date_start.format_display() if nb.date_start else "?"
                b = nb.date_end.format_display() if nb.date_end else "?"
                st.caption(f"{a} → {b}")
            else:
                st.caption("Undated")
            rate = (
                f"{nb.pages_per_day} pages/day"
                if nb.pages_per_day is not None
                else "writing rate unavailable"
            )
            st.caption(f"{nb.page_count} pages ({rate})")
            if nb.activity:
                grain = "month"
                if nb.activity and "W" in nb.activity[0].key:
                    grain = "week"
                elif nb.activity and len(nb.activity[0].key) == 4:
                    grain = "year"
                elif nb.activity and len(nb.activity[0].key) == 10:
                    grain = "day"
                _activity_chart(nb.activity, grain, height=120)
            b1, b2 = st.columns(2)
            if project and b1.button("Browse pages", key=f"nb_browse_{nb.project_id}"):
                page_ids = [p.page_id for p in project.pages]
                open_page_context(
                    page_id=page_ids[0],
                    page_ids=page_ids,
                    project_root=nb.root,
                    return_mode="Notebooks",
                )
                st.rerun()
            if b2.button("Open workflow", key=f"nb_open_{nb.project_id}"):
                st.session_state["root"] = str(nb.root)
                st.session_state["ui_mode"] = "Workflow"
                st.rerun()
        st.divider()


def render_search(runtime: RuntimePaths, archive: ArchiveService) -> None:
    del runtime
    archive.ensure_index()
    st.subheader("Search")
    query = st.text_input("Search text", value=st.session_state.get("search_query", ""))
    st.session_state["search_query"] = query
    order = st.selectbox(
        "Order",
        ["oldest", "newest"],
        format_func=lambda x: "Oldest first" if x == "oldest" else "Newest first",
        key="search_order",
    )
    tag_filter = st.text_input("Tags (comma-separated, AND)", key="search_tags")
    tags = tuple(t.strip().lower() for t in tag_filter.split(",") if t.strip())
    include_undated = st.checkbox("Include undated", value=True, key="search_undated")

    inventory = archive.type_inventory()
    media_keys = [t.key for t in inventory if t.kind == "media_type"]
    selected_media = st.multiselect("Media types", media_keys, default=media_keys)

    page_size = 50
    # Reset offset when query/filters change.
    filter_sig = f"{query}|{order}|{tags}|{selected_media}|{include_undated}"
    if st.session_state.get("search_filter_sig") != filter_sig:
        st.session_state["search_filter_sig"] = filter_sig
        st.session_state["search_offset"] = 0
    offset = int(st.session_state.get("search_offset", 0))

    filters = ArchiveFilters(
        query="",
        tags=tags,
        media_types=tuple(selected_media) if set(selected_media) != set(media_keys) else (),
        include_undated=include_undated,
    )
    result = archive.search(
        query, order=order, filters=filters, limit=page_size, offset=offset  # type: ignore[arg-type]
    )
    if result.total_matched == 0:
        st.markdown("**0** results")
        st.info("No matching pages.")
        return

    start = result.offset + 1
    end = result.offset + result.showing
    st.markdown(f"Showing **{start}–{end}** of **{result.total_matched}**")

    entries = [
        {"page_id": h.page_id, "project_root": str(h.project_root)} for h in result.hits
    ]
    # Preserve full nav list across Load more by accumulating in session.
    if offset == 0:
        st.session_state["search_nav_entries"] = entries
    else:
        prev = st.session_state.get("search_nav_entries") or []
        seen = {e["page_id"] for e in prev}
        st.session_state["search_nav_entries"] = prev + [
            e for e in entries if e["page_id"] not in seen
        ]

    for hit in result.hits:
        cols = st.columns([3, 1])
        date_s = hit.date.format_display() if hit.date else "Undated"
        cols[0].markdown(
            f"**{hit.project_title}** · p.{hit.page_index_in_notebook}/"
            f"{hit.notebook_page_count} · {date_s}"
        )
        if hit.snippet:
            cols[0].caption(hit.snippet)
        if hit.tags:
            cols[0].caption("Tags: " + ", ".join(hit.tags))
        if cols[1].button("Open", key=f"search_open_{hit.page_id}"):
            # Build full matched nav list (capped) so Prev/Next crosses all hits,
            # not only the current results page.
            nav_limit = min(max(result.total_matched, 1), 2000)
            full = archive.search(
                query,
                order=order,  # type: ignore[arg-type]
                filters=filters,
                limit=nav_limit,
                offset=0,
            )
            nav = [
                {"page_id": h.page_id, "project_root": str(h.project_root)}
                for h in full.hits
            ]
            if not any(e["page_id"] == hit.page_id for e in nav):
                nav.insert(
                    0,
                    {"page_id": hit.page_id, "project_root": str(hit.project_root)},
                )
            open_page_context(
                page_id=hit.page_id,
                page_ids=[e["page_id"] for e in nav],
                project_root=hit.project_root,
                highlight=query,
                return_mode="Search",
                view_entries=nav,
            )
            st.rerun()

    c1, c2 = st.columns(2)
    if offset > 0 and c1.button("Previous page"):
        st.session_state["search_offset"] = max(0, offset - page_size)
        st.rerun()
    if end < result.total_matched and c2.button("Load more"):
        st.session_state["search_offset"] = offset + page_size
        st.rerun()
