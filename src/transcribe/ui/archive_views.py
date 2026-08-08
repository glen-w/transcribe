"""Archive, notebook browser, and search Streamlit views."""

from __future__ import annotations

import streamlit as st

from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.archive import ArchiveFilters, ArchiveService, NotebookSummary
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


def render_archive(runtime: RuntimePaths, archive: ArchiveService) -> None:
    from transcribe.ui.page_viewer import _parse_date_input

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

    inventory = archive.type_inventory(ArchiveFilters(include_undated=True))
    media_keys = [t.key for t in inventory if t.kind == "media_type"]
    project_tag_keys = [t.key for t in inventory if t.kind == "project_tag"]

    selected_media: list[str] = []
    selected_project_tags: list[str] = []
    if media_keys or project_tag_keys:
        st.caption("Types")
        cols = st.columns(max(1, min(6, len(media_keys) + len(project_tag_keys))))
        i = 0
        for key in media_keys:
            total = next(t.total for t in inventory if t.key == key and t.kind == "media_type")
            if cols[i % len(cols)].checkbox(f"{key} ({total})", value=True, key=f"arc_mt_{key}"):
                selected_media.append(key)
            i += 1
        for key in project_tag_keys:
            total = next(t.total for t in inventory if t.key == key and t.kind == "project_tag")
            if cols[i % len(cols)].checkbox(
                f"tag:{key} ({total})", value=True, key=f"arc_pt_{key}"
            ):
                selected_project_tags.append(key)
            i += 1

    # When all media boxes checked (or none exist), do not restrict by media_type.
    if selected_media and media_keys and set(selected_media) == set(media_keys):
        selected_media = []
    if (
        selected_project_tags
        and project_tag_keys
        and set(selected_project_tags) == set(project_tag_keys)
    ):
        selected_project_tags = []

    tag_filter = st.text_input("Tag filter (comma-separated, page or notebook tags)", "")
    selected_tags = [t.strip() for t in tag_filter.split(",") if t.strip()]

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
        chart_data = {
            "bin": [b.key for b in timeline.bins],
            "pages": [b.count for b in timeline.bins],
        }
        st.bar_chart(chart_data, x="bin", y="pages", height=220)
        st.caption(f"Activity by {timeline.grain}")
    else:
        st.info("No dated pages match the current filters.")

    notebooks = archive.list_notebooks(order="oldest", filters=filters)
    st.markdown("#### Notebooks")
    if not notebooks:
        st.caption("No notebooks yet. Create a project under the projects root.")
        return

    strip = notebooks[:12]
    cols = st.columns(len(strip))
    for col, nb in zip(cols, strip):
        with col:
            _notebook_card(nb, return_mode="Archive")


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
    if st.button("Open", key=f"open_nb_{nb.project_id}_{return_mode}"):
        st.session_state["root"] = str(nb.root)
        st.session_state["ui_mode"] = "Workflow"
        st.session_state["show_page_viewer"] = False
        st.rerun()
    if cover_id and st.button("View cover page", key=f"view_nb_{nb.project_id}_{return_mode}"):
        page_ids = [p.page_id for p in project.pages]
        open_page_context(
            page_id=cover_id,
            page_ids=page_ids,
            project_root=nb.root,
            return_mode=return_mode,
        )
        st.session_state["ui_mode"] = return_mode
        st.rerun()


def render_notebooks(runtime: RuntimePaths, archive: ArchiveService) -> None:
    del runtime  # reserved for future inbox/export shortcuts
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
                st.bar_chart(
                    {
                        "when": [b.key for b in nb.activity],
                        "pages": [b.count for b in nb.activity],
                    },
                    x="when",
                    y="pages",
                    height=120,
                )
            b1, b2 = st.columns(2)
            if b1.button("Open notebook", key=f"nb_open_{nb.project_id}"):
                st.session_state["root"] = str(nb.root)
                st.session_state["ui_mode"] = "Workflow"
                st.rerun()
            if project and b2.button("Browse pages", key=f"nb_browse_{nb.project_id}"):
                page_ids = [p.page_id for p in project.pages]
                open_page_context(
                    page_id=page_ids[0],
                    page_ids=page_ids,
                    project_root=nb.root,
                    return_mode="Notebooks",
                )
                st.rerun()
        st.divider()


def render_search(runtime: RuntimePaths, archive: ArchiveService) -> None:
    del runtime
    st.subheader("Search")
    query = st.text_input("Search text", value=st.session_state.get("search_query", ""))
    st.session_state["search_query"] = query
    order = st.selectbox(
        "Order",
        ["oldest", "newest"],
        format_func=lambda x: "Oldest first" if x == "oldest" else "Newest first",
        key="search_order",
    )
    tag_filter = st.text_input("Tags (comma-separated)", key="search_tags")
    tags = tuple(t.strip().lower() for t in tag_filter.split(",") if t.strip())
    include_undated = st.checkbox("Include undated", value=True, key="search_undated")

    inventory = archive.type_inventory()
    media_keys = [t.key for t in inventory if t.kind == "media_type"]
    selected_media = st.multiselect("Media types", media_keys, default=media_keys)

    filters = ArchiveFilters(
        query="",
        tags=tags,
        media_types=tuple(selected_media) if set(selected_media) != set(media_keys) else (),
        include_undated=include_undated,
    )
    result = archive.search(query, order=order, filters=filters)  # type: ignore[arg-type]
    st.markdown(f"**{result.showing}** results")

    if not result.hits:
        st.info("No matching pages.")
        return

    st.session_state["search_hit_ids"] = [h.page_id for h in result.hits]
    st.session_state["search_hit_roots"] = {h.page_id: str(h.project_root) for h in result.hits}

    for hit in result.hits[:100]:
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
            same = [h for h in result.hits if h.project_id == hit.project_id]
            open_page_context(
                page_id=hit.page_id,
                page_ids=[h.page_id for h in same],
                project_root=hit.project_root,
                highlight=query,
                return_mode="Search",
            )
            st.rerun()
