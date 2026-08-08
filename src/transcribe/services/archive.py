"""Workspace archive queries: timeline, notebook summaries, and search.

Index is derived (SQLite FTS). User identity remains page_id / project.id on disk.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from transcribe.domain.dates import (
    ApproximateDate,
    max_date,
    min_date,
    normalize_tags,
    pages_per_day,
)
from transcribe.domain.models import Project
from transcribe.errors import ProjectError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths

NotebookOrder = Literal["oldest", "newest", "most_pages"]
SearchOrder = Literal["oldest", "newest"]
PeriodKind = Literal["all", "year", "range"]


@dataclass(frozen=True)
class ArchiveFilters:
    period: PeriodKind = "all"
    year: int | None = None
    range_start: ApproximateDate | None = None
    range_end: ApproximateDate | None = None
    query: str = ""
    tags: tuple[str, ...] = ()
    media_types: tuple[str, ...] = ()
    project_tags: tuple[str, ...] = ()
    notebook_ids: tuple[str, ...] = ()
    include_undated: bool = True


@dataclass
class TypeCount:
    key: str
    kind: str  # "media_type" | "project_tag"
    total: int
    selected: int


@dataclass
class TimelineBin:
    key: str
    count: int


@dataclass
class TimelineResult:
    bins: list[TimelineBin]
    showing: int
    total: int
    undated_count: int
    dated_count: int
    type_counts: list[TypeCount]
    grain: str


@dataclass
class ActivityBin:
    key: str
    count: int


@dataclass
class NotebookSummary:
    project_id: str
    title: str
    root: Path
    page_count: int
    tags: list[str]
    cover_page_id: str | None
    date_start: ApproximateDate | None
    date_end: ApproximateDate | None
    pages_per_day: float | None
    activity: list[ActivityBin] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)


@dataclass
class SearchHit:
    page_id: str
    project_id: str
    project_title: str
    project_root: Path
    page_index_in_notebook: int
    notebook_page_count: int
    date: ApproximateDate | None
    tags: list[str]
    snippet: str
    media_type: str


@dataclass
class SearchResult:
    hits: list[SearchHit]
    showing: int
    total_indexed: int


def discover_project_roots(projects_dir: Path) -> list[Path]:
    if not projects_dir.exists():
        return []
    roots: list[Path] = []
    for child in sorted(projects_dir.iterdir()):
        if child.is_dir() and (child / "project.json").exists():
            roots.append(child.resolve())
    return roots


def _source_media_type(project: Project, source_id: str) -> str:
    for source in project.sources:
        if source.source_id == source_id:
            # Normalize common MIME / short labels into stable filter keys.
            mt = (source.media_type or "").lower()
            if "pdf" in mt:
                return "pdf"
            if "image" in mt or mt in {"jpeg", "jpg", "png", "image"}:
                return "image"
            return mt or "unknown"
    return "unknown"


def _notebook_bounds(project: Project) -> tuple[ApproximateDate | None, ApproximateDate | None]:
    if project.date_start is not None or project.date_end is not None:
        return project.date_start, project.date_end
    dated = [p.date for p in project.pages if p.date is not None]
    return min_date(dated), max_date(dated)  # type: ignore[arg-type]


def _page_in_period(page_date: ApproximateDate | None, filters: ArchiveFilters) -> bool:
    if page_date is None:
        # Undated pages only appear when browsing the full archive with the toggle on.
        if filters.period != "all":
            return False
        return filters.include_undated
    if filters.period == "all":
        return True
    if filters.period == "year":
        return filters.year is not None and page_date.year == filters.year
    # range
    if filters.range_start is not None and page_date.sort_key() < filters.range_start.sort_key():
        return False
    if filters.range_end is not None and page_date.sort_key() > filters.range_end.sort_key():
        return False
    return True


def _choose_grain(dates: list[ApproximateDate]) -> str:
    if not dates:
        return "month"
    years = {d.year for d in dates}
    if len(years) >= 3:
        return "month"
    if len(years) == 1:
        months = {(d.year, d.month or 1) for d in dates}
        return "day" if len(months) <= 2 else "week"
    return "month"


class ArchiveService:
    def __init__(self, runtime: RuntimePaths) -> None:
        self.runtime = runtime
        self.runtime.ensure_layout()
        self.index_path = self.runtime.data_dir / "cache" / "archive.sqlite"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.index_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notebooks (
              project_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              root TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              cover_page_id TEXT,
              date_start_json TEXT,
              date_end_json TEXT,
              page_count INTEGER NOT NULL,
              signature TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pages (
              page_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              page_ord INTEGER NOT NULL,
              source_id TEXT NOT NULL,
              media_type TEXT NOT NULL,
              date_json TEXT,
              sort_key TEXT,
              tags_json TEXT NOT NULL,
              text TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES notebooks(project_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id);
            CREATE INDEX IF NOT EXISTS idx_pages_sort ON pages(sort_key);
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
              page_id UNINDEXED,
              project_id UNINDEXED,
              text,
              tags,
              title,
              content=''
            );
            """
        )

    def _project_signature(self, root: Path, project: Project) -> str:
        parts = [project.updated_at, str(len(project.pages))]
        results = root / "results"
        if results.exists():
            mtimes = sorted(f"{p.name}:{p.stat().st_mtime_ns}" for p in results.glob("*.json"))
            parts.extend(mtimes)
        return "|".join(parts)

    def ensure_index(self) -> None:
        roots = discover_project_roots(self.runtime.projects_dir)
        with self._connect() as conn:
            self._ensure_schema(conn)
            known = {
                row["project_id"]: row["signature"]
                for row in conn.execute("SELECT project_id, signature FROM notebooks")
            }
            seen: set[str] = set()
            for root in roots:
                try:
                    paths = open_project_paths(root)
                    projects = ProjectService(
                        paths, clock=SystemClock(), ids=UuidGenerator()
                    )
                    project = projects.load(reconcile=False)
                except (ProjectError, OSError, ValueError):
                    continue
                sig = self._project_signature(root, project)
                seen.add(project.id)
                if known.get(project.id) == sig:
                    continue
                self._reindex_project(conn, root, project, projects, sig)
            stale = set(known) - seen
            for project_id in stale:
                conn.execute("DELETE FROM notebooks WHERE project_id = ?", (project_id,))
                conn.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
                conn.execute("DELETE FROM pages_fts WHERE project_id = ?", (project_id,))
            conn.commit()

    def invalidate(self, project_id: str) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM notebooks WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM pages_fts WHERE project_id = ?", (project_id,))
            conn.commit()

    def _reindex_project(
        self,
        conn: sqlite3.Connection,
        root: Path,
        project: Project,
        projects: ProjectService,
        signature: str,
    ) -> None:
        conn.execute("DELETE FROM pages_fts WHERE project_id = ?", (project.id,))
        conn.execute("DELETE FROM pages WHERE project_id = ?", (project.id,))
        conn.execute("DELETE FROM notebooks WHERE project_id = ?", (project.id,))
        start, end = _notebook_bounds(project)
        conn.execute(
            """
            INSERT INTO notebooks(
              project_id, title, root, updated_at, tags_json, cover_page_id,
              date_start_json, date_end_json, page_count, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.title,
                str(root),
                project.updated_at,
                json.dumps(project.tags),
                project.cover_page_id,
                json.dumps(start.as_dict()) if start else None,
                json.dumps(end.as_dict()) if end else None,
                len(project.pages),
                signature,
            ),
        )
        for ord_i, page in enumerate(project.pages):
            result = projects.load_page_result(page.page_id)
            text = (result.effective_text() if result else None) or ""
            media = _source_media_type(project, page.source_id)
            date_json = json.dumps(page.date.as_dict()) if page.date else None
            sort_key = (
                f"{page.date.sort_key()[0]:04d}-{page.date.sort_key()[1]:02d}-"
                f"{page.date.sort_key()[2]:02d}"
                if page.date
                else None
            )
            tags = normalize_tags([*project.tags, *page.tags])
            conn.execute(
                """
                INSERT INTO pages(
                  page_id, project_id, page_ord, source_id, media_type,
                  date_json, sort_key, tags_json, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page.page_id,
                    project.id,
                    ord_i,
                    page.source_id,
                    media,
                    date_json,
                    sort_key,
                    json.dumps(tags),
                    text,
                ),
            )
            conn.execute(
                """
                INSERT INTO pages_fts(page_id, project_id, text, tags, title)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    page.page_id,
                    project.id,
                    text,
                    " ".join(tags),
                    project.title,
                ),
            )

    def _load_page_rows(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return list(
            conn.execute(
                """
                SELECT p.*, n.title AS project_title, n.root AS project_root,
                       n.tags_json AS project_tags_json, n.page_count AS notebook_page_count
                FROM pages p
                JOIN notebooks n ON n.project_id = p.project_id
                """
            )
        )

    def _parse_date(self, raw: str | None) -> ApproximateDate | None:
        if not raw:
            return None
        return ApproximateDate.from_dict(json.loads(raw))

    def _row_matches(self, row: sqlite3.Row, filters: ArchiveFilters) -> bool:
        page_date = self._parse_date(row["date_json"])
        if not _page_in_period(page_date, filters):
            return False
        if filters.notebook_ids and row["project_id"] not in filters.notebook_ids:
            return False
        if filters.media_types and row["media_type"] not in filters.media_types:
            return False
        tags = set(json.loads(row["tags_json"] or "[]"))
        project_tags = set(json.loads(row["project_tags_json"] or "[]"))
        if filters.tags and not set(filters.tags).issubset(tags):
            return False
        if filters.project_tags and not set(filters.project_tags).issubset(project_tags):
            return False
        q = filters.query.strip().lower()
        if q:
            hay = f"{row['text']} {row['project_title']} {' '.join(tags)}".lower()
            if q not in hay:
                return False
        return True

    def available_years(self) -> list[int]:
        self.ensure_index()
        with self._connect() as conn:
            years: set[int] = set()
            for row in conn.execute("SELECT date_json FROM pages WHERE date_json IS NOT NULL"):
                d = self._parse_date(row["date_json"])
                if d:
                    years.add(d.year)
            return sorted(years)

    def type_inventory(self, filters: ArchiveFilters | None = None) -> list[TypeCount]:
        self.ensure_index()
        filters = filters or ArchiveFilters()
        with self._connect() as conn:
            rows = self._load_page_rows(conn)
            media_totals: dict[str, int] = {}
            media_sel: dict[str, int] = {}
            tag_totals: dict[str, int] = {}
            tag_sel: dict[str, int] = {}
            for row in rows:
                mt = row["media_type"]
                media_totals[mt] = media_totals.get(mt, 0) + 1
                for t in json.loads(row["project_tags_json"] or "[]"):
                    tag_totals[t] = tag_totals.get(t, 0) + 1
                if self._row_matches(row, filters):
                    media_sel[mt] = media_sel.get(mt, 0) + 1
                    for t in json.loads(row["project_tags_json"] or "[]"):
                        tag_sel[t] = tag_sel.get(t, 0) + 1
            out: list[TypeCount] = []
            for key in sorted(media_totals):
                out.append(
                    TypeCount(
                        key=key,
                        kind="media_type",
                        total=media_totals[key],
                        selected=media_sel.get(key, 0),
                    )
                )
            for key in sorted(tag_totals):
                out.append(
                    TypeCount(
                        key=key,
                        kind="project_tag",
                        total=tag_totals[key],
                        selected=tag_sel.get(key, 0),
                    )
                )
            return out

    def timeline(self, filters: ArchiveFilters | None = None) -> TimelineResult:
        self.ensure_index()
        filters = filters or ArchiveFilters()
        with self._connect() as conn:
            rows = self._load_page_rows(conn)
            total = len(rows)
            matched = [r for r in rows if self._row_matches(r, filters)]
            dated_dates: list[ApproximateDate] = []
            undated = 0
            for row in matched:
                d = self._parse_date(row["date_json"])
                if d is None:
                    undated += 1
                else:
                    dated_dates.append(d)
            grain = _choose_grain(dated_dates)
            counts: dict[str, int] = {}
            for d in dated_dates:
                key = d.bin_key(grain)
                counts[key] = counts.get(key, 0) + 1
            bins = [TimelineBin(key=k, count=counts[k]) for k in sorted(counts)]
            # Type counts relative to current non-type filters for the UI strip.
            type_filters = ArchiveFilters(
                period=filters.period,
                year=filters.year,
                range_start=filters.range_start,
                range_end=filters.range_end,
                query=filters.query,
                tags=filters.tags,
                notebook_ids=filters.notebook_ids,
                include_undated=filters.include_undated,
            )
            return TimelineResult(
                bins=bins,
                showing=len(matched),
                total=total,
                undated_count=undated,
                dated_count=len(dated_dates),
                type_counts=self.type_inventory(type_filters),
                grain=grain,
            )

    def list_notebooks(
        self,
        *,
        order: NotebookOrder = "oldest",
        filters: ArchiveFilters | None = None,
    ) -> list[NotebookSummary]:
        self.ensure_index()
        filters = filters or ArchiveFilters()
        with self._connect() as conn:
            notebooks = list(conn.execute("SELECT * FROM notebooks"))
            pages = self._load_page_rows(conn)
            by_project: dict[str, list[sqlite3.Row]] = {}
            for row in pages:
                by_project.setdefault(row["project_id"], []).append(row)

            summaries: list[NotebookSummary] = []
            for nb in notebooks:
                proj_pages = by_project.get(nb["project_id"], [])
                matched = [r for r in proj_pages if self._row_matches(r, filters)]
                if filters.query or filters.tags or filters.media_types or filters.project_tags:
                    if not matched and proj_pages:
                        # Hide notebooks with zero matching pages under active filters.
                        continue
                elif filters.notebook_ids and nb["project_id"] not in filters.notebook_ids:
                    continue

                dated = [self._parse_date(r["date_json"]) for r in matched]
                dated_only = [d for d in dated if d is not None]
                start = self._parse_date(nb["date_start_json"])
                end = self._parse_date(nb["date_end_json"])
                if start is None and end is None:
                    start, end = min_date(dated_only), max_date(dated_only)

                grain = _choose_grain(dated_only) if dated_only else "month"
                activity_counts: dict[str, int] = {}
                for d in dated_only:
                    key = d.bin_key(grain)
                    activity_counts[key] = activity_counts.get(key, 0) + 1
                activity = [
                    ActivityBin(key=k, count=activity_counts[k]) for k in sorted(activity_counts)
                ]
                media = sorted({r["media_type"] for r in proj_pages})
                cover = nb["cover_page_id"]
                if not cover and proj_pages:
                    cover = proj_pages[0]["page_id"]
                page_count = len(proj_pages)
                summaries.append(
                    NotebookSummary(
                        project_id=nb["project_id"],
                        title=nb["title"],
                        root=Path(nb["root"]),
                        page_count=page_count,
                        tags=json.loads(nb["tags_json"] or "[]"),
                        cover_page_id=cover,
                        date_start=start,
                        date_end=end,
                        pages_per_day=pages_per_day(page_count, start, end),
                        activity=activity,
                        media_types=media,
                    )
                )

            def sort_key(s: NotebookSummary) -> tuple:
                if order == "most_pages":
                    return (-s.page_count, s.title.lower())
                start_key = s.date_start.sort_key() if s.date_start else (9999, 99, 99)
                if order == "newest":
                    end_key = s.date_end.sort_key() if s.date_end else (0, 0, 0)
                    return (-end_key[0], -end_key[1], -end_key[2], s.title.lower())
                return (*start_key, s.title.lower())

            summaries.sort(key=sort_key)
            return summaries

    def notebook_activity(self, project_id: str) -> list[ActivityBin]:
        notebooks = self.list_notebooks(
            filters=ArchiveFilters(notebook_ids=(project_id,), include_undated=True)
        )
        return notebooks[0].activity if notebooks else []

    def search(
        self,
        query: str,
        *,
        order: SearchOrder = "oldest",
        filters: ArchiveFilters | None = None,
    ) -> SearchResult:
        self.ensure_index()
        base = filters or ArchiveFilters()
        # Merge free-text into filters for consistent matching.
        merged = ArchiveFilters(
            period=base.period,
            year=base.year,
            range_start=base.range_start,
            range_end=base.range_end,
            query=query if query.strip() else base.query,
            tags=base.tags,
            media_types=base.media_types,
            project_tags=base.project_tags,
            notebook_ids=base.notebook_ids,
            include_undated=base.include_undated,
        )
        with self._connect() as conn:
            rows = self._load_page_rows(conn)
            total = len(rows)
            matched = [r for r in rows if self._row_matches(r, merged)]

            def hit_sort_key(row: sqlite3.Row) -> tuple:
                d = self._parse_date(row["date_json"])
                if d is None:
                    key = (9999, 99, 99)
                else:
                    key = d.sort_key()
                if order == "newest":
                    return (-key[0], -key[1], -key[2], row["page_ord"])
                return (*key, row["page_ord"])

            matched.sort(key=hit_sort_key)
            q = merged.query.strip()
            hits: list[SearchHit] = []
            for row in matched:
                text = row["text"] or ""
                snippet = _snippet(text, q)
                hits.append(
                    SearchHit(
                        page_id=row["page_id"],
                        project_id=row["project_id"],
                        project_title=row["project_title"],
                        project_root=Path(row["project_root"]),
                        page_index_in_notebook=int(row["page_ord"]) + 1,
                        notebook_page_count=int(row["notebook_page_count"]),
                        date=self._parse_date(row["date_json"]),
                        tags=json.loads(row["tags_json"] or "[]"),
                        snippet=snippet,
                        media_type=row["media_type"],
                    )
                )
            return SearchResult(hits=hits, showing=len(hits), total_indexed=total)


_WORD_RE = re.compile(r"\s+")


def _snippet(text: str, query: str, radius: int = 80) -> str:
    compact = _WORD_RE.sub(" ", text).strip()
    if not compact:
        return ""
    if not query:
        return compact[: radius * 2] + ("…" if len(compact) > radius * 2 else "")
    lower = compact.lower()
    q = query.lower()
    idx = lower.find(q)
    if idx < 0:
        return compact[: radius * 2] + ("…" if len(compact) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(compact), idx + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(compact) else ""
    return prefix + compact[start:end] + suffix


def highlight_terms(text: str, query: str) -> str:
    """Return markdown-ish highlighted text for Streamlit display (simple case-insensitive)."""
    if not query.strip() or not text:
        return text
    pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)
    return pattern.sub(lambda m: f"**{m.group(0)}**", text)
