"""Archive, notebook browser, and search Streamlit views."""

from __future__ import annotations

import hashlib
from pathlib import Path

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
from transcribe.ui.action_menus.catalog import help_for
from transcribe.ui.action_menus.context import ActionContext
from transcribe.ui.action_menus.ids import ActionId, NavStyle, ReturnMode, SectionId
from transcribe.ui.action_menus.nav import load_live_notebook_context, navigate_open
from transcribe.ui.action_menus.render import render_configured_actions
from transcribe.ui.page_viewer import open_page_context

# Layout slots (no crop): View pins width beside the chart; Archive pins height in the strip.
VIEW_COVER_WIDTH_PX = 112
VIEW_ROW_CHART_HEIGHT = 120
ARCHIVE_COVER_HEIGHT_PX = 160


def _cover_open_key(instance_prefix: str, project_id: str) -> str:
    digest = hashlib.sha1(
        f"{instance_prefix}|{project_id}|cover_open".encode()
    ).hexdigest()[:10]
    return f"tx_cover_{instance_prefix}_{project_id}_{digest}"


def _render_clickable_cover(
    thumb: Path,
    ctx: ActionContext,
    *,
    key: str,
    width: int | str = "stretch",
) -> None:
    """Cover thumbnail: click runs the same navigation as the Open action."""
    st.image(str(thumb), width=width)
    can_open = bool(ctx.project_exists and ctx.has_pages and ctx.page_ids)
    if st.button(
        "Open",
        key=key,
        type="tertiary",
        width="stretch",
        disabled=not can_open,
        help=help_for(ActionId.OPEN) if can_open else "No pages to open.",
    ):
        if navigate_open(ctx, rerun=False):
            st.rerun()


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
    axis_format = {
        "day": "%d %b %Y",
        "week": "%d %b %Y",
        "month": "%b %Y",
        "year": "%Y",
    }.get(grain, "%b %Y")
    tick_count = min(10, max(4, len(bins)))
    try:
        import altair as alt
        import pandas as pd

        rows = [
            {
                "when": pd.Timestamp(bin_key_to_date(b.key, grain)),
                "pages": b.count,
                "label": b.key,
            }
            for b in bins
        ]
        df = pd.DataFrame(rows)
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "when:T",
                    title=None,
                    axis=alt.Axis(
                        format=axis_format,
                        labelAngle=-35,
                        labelOverlap=True,
                        tickCount=tick_count,
                        grid=False,
                    ),
                ),
                y=alt.Y("pages:Q", title="Pages"),
                tooltip=[
                    alt.Tooltip("when:T", title="When", format=axis_format),
                    alt.Tooltip("pages:Q", title="Pages"),
                ],
            )
            .properties(height=height)
        )
        st.altair_chart(chart, width="stretch")
    except Exception:
        # Readable categorical fallback when Altair/pandas is unavailable.
        labels = []
        for b in bins:
            d = bin_key_to_date(b.key, grain)
            if grain == "year":
                labels.append(f"{d.year}")
            elif grain == "month":
                labels.append(d.strftime("%b %Y"))
            else:
                labels.append(d.strftime("%d %b %Y"))
        st.bar_chart(
            {"when": labels, "pages": [b.count for b in bins]},
            x="when",
            y="pages",
            height=height,
        )


def render_archive(runtime: RuntimePaths, archive: ArchiveService) -> None:
    from transcribe.domain.dates import parse_date_input

    archive.ensure_index()
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
            range_start = parse_date_input(start_raw) if start_raw.strip() else None
            range_end = parse_date_input(end_raw) if end_raw.strip() else None
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
    excluded = timeline.showing - timeline.dated_count
    if excluded <= 0:
        spike_note = ""
    elif excluded == timeline.undated_count:
        spike_note = f" · {excluded} undated (excluded from spikes)"
    else:
        spike_note = f" · {excluded} undated/out-of-range (excluded from spikes)"
    st.markdown(
        f"Showing **{timeline.showing}** of **{timeline.total}** pages" + spike_note
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
            _notebook_card(
                nb,
                projects_dir=runtime.projects_dir,
                return_mode=ReturnMode.ARCHIVE,
            )
    if show_n < len(notebooks):
        if st.button(f"Show more notebooks ({len(notebooks) - show_n} remaining)"):
            st.session_state["archive_strip_n"] = show_n + 12
            st.rerun()
    elif show_n > 12:
        if st.button("Show fewer"):
            st.session_state["archive_strip_n"] = 12
            st.rerun()


def _notebook_card(
    nb: NotebookSummary,
    *,
    projects_dir,
    return_mode: ReturnMode,
) -> None:
    try:
        ctx = load_live_notebook_context(
            project_id=nb.project_id,
            project_root=nb.root,
            projects_dir=projects_dir,
            return_mode=return_mode,
            nav_style=NavStyle.CLICK_RERUN,
            instance_prefix="archive",
        )
    except Exception:  # noqa: BLE001
        ctx = None

    try:
        paths = open_project_paths(nb.root)
        projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
        project = projects.load(reconcile=False)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"{nb.title}: {exc}")
        if ctx is not None:
            try:
                render_configured_actions(SectionId.ARCHIVE_NOTEBOOK, ctx)
            except Exception:  # noqa: BLE001
                st.caption("Actions unavailable.")
        else:
            st.caption("Actions unavailable.")
        return

    if ctx is not None:
        thumbs = ThumbnailService(paths)
        cover_id = thumbs.cover_page_id(project)
        if cover_id:
            thumb = thumbs.ensure_thumb(project, cover_id)
            if thumb and thumb.exists():
                _render_clickable_cover(
                    thumb,
                    ctx,
                    key=_cover_open_key("archive", nb.project_id),
                    width="content",
                )
    date_label = "Undated"
    if nb.date_start or nb.date_end:
        a = nb.date_start.format_display() if nb.date_start else "?"
        b = nb.date_end.format_display() if nb.date_end else "?"
        date_label = f"{a} → {b}"
    st.caption(nb.title)
    st.caption(date_label)
    rate = f"{nb.pages_per_day} pages/day" if nb.pages_per_day is not None else "rate n/a"
    st.caption(f"{nb.page_count} pages · {rate}")
    if ctx is not None:
        try:
            render_configured_actions(SectionId.ARCHIVE_NOTEBOOK, ctx)
        except Exception:  # noqa: BLE001
            st.caption("Actions unavailable.")
    else:
        st.caption("Actions unavailable.")


def render_notebooks(runtime: RuntimePaths, archive: ArchiveService) -> None:
    archive.ensure_index()
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
        try:
            ctx = load_live_notebook_context(
                project_id=nb.project_id,
                project_root=nb.root,
                projects_dir=runtime.projects_dir,
                return_mode=ReturnMode.VIEW,
                nav_style=NavStyle.CLICK_RERUN,
                instance_prefix="view",
            )
        except Exception:  # noqa: BLE001
            ctx = None
        # Narrow cover column; chart/actions take the rest. Cover width is fixed in px.
        left, right = st.columns([1, 8], gap="medium")
        with left:
            paths = open_project_paths(nb.root)
            projects = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
            try:
                project = projects.load(reconcile=False)
            except Exception:
                project = None
            if project is not None and ctx is not None:
                thumbs = ThumbnailService(paths)
                cover_id = thumbs.cover_page_id(project)
                if cover_id:
                    thumb = thumbs.ensure_thumb(project, cover_id)
                    if thumb and thumb.exists():
                        _render_clickable_cover(
                            thumb,
                            ctx,
                            key=_cover_open_key("view", nb.project_id),
                            width=VIEW_COVER_WIDTH_PX,
                        )
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
                _activity_chart(nb.activity, grain, height=VIEW_ROW_CHART_HEIGHT)
            if ctx is not None:
                try:
                    render_configured_actions(SectionId.VIEW_NOTEBOOK, ctx)
                except Exception:  # noqa: BLE001
                    st.caption("Actions unavailable.")
            else:
                st.caption("Actions unavailable.")
        st.divider()


def render_search(runtime: RuntimePaths, archive: ArchiveService) -> None:
    del runtime
    archive.ensure_index()
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
