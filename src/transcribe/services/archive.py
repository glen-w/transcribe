"""Workspace archive queries: timeline, notebook summaries, and search.

Index is disposable derived state (SQLite FTS cache). User identity and
authority remain page_id / project.id / project.json on disk. Project
signatures use mtime rollups intentionally — acceptable only because this
layer is a rebuildable cache, never a source of truth.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from transcribe.domain.dates import (
    ApproximateDate,
    fill_bin_series,
    is_plausible_diary_year,
    max_date,
    min_date,
    normalize_tags,
    pages_per_day,
)
from transcribe.domain.models import Project
from transcribe.errors import ProjectError
from transcribe.markdown_plain import escape_markdown_plain
from transcribe.persistence.locks import FileLock
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths

NotebookOrder = Literal["oldest", "newest", "most_pages"]
SearchOrder = Literal["oldest", "newest"]
PeriodKind = Literal["all", "year", "range"]

_INDEX_TTL_S = 2.0
_FTS_SCHEMA_VERSION = 2
_CACHE_SCHEMA_VERSION = 1
_BUSY_TIMEOUT_MS = 5000
_GENERATION_FILENAME = "archive.generation"


def archive_generation_path(runtime: RuntimePaths) -> Path:
    return runtime.data_dir / "cache" / _GENERATION_FILENAME


def read_archive_generation(runtime: RuntimePaths) -> int:
    """Workspace mutation token for cheap ensure_index short-circuit."""
    path = archive_generation_path(runtime)
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def bump_archive_generation(runtime: RuntimePaths) -> int:
    """Increment the workspace mutation token (call after project text/index mutations)."""
    path = archive_generation_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path.with_suffix(".generation.lock"), timeout=30.0)
    with lock:
        current = read_archive_generation(runtime)
        nxt = current + 1
        tmp = path.with_suffix(".generation.tmp")
        tmp.write_text(str(nxt), encoding="utf-8")
        tmp.replace(path)
        return nxt


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
    total_matched: int
    total_indexed: int
    offset: int
    limit: int


def discover_project_roots(projects_dir: Path) -> list[Path]:
    if not projects_dir.exists():
        return []
    roots: list[Path] = []
    for child in sorted(projects_dir.iterdir()):
        if child.is_dir() and (child / "project.json").exists():
            roots.append(child.resolve())
    return roots


def discover_corpus_project_roots(runtime: RuntimePaths) -> list[Path]:
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.services.corpus_registry import discover_roots

    return discover_roots(CorpusPaths.from_runtime(runtime))


def _source_media_type(project: Project, source_id: str) -> str:
    for source in project.sources:
        if source.source_id == source_id:
            mt = (source.media_type or "").lower()
            if "pdf" in mt:
                return "pdf"
            if "image" in mt or mt in {"jpeg", "jpg", "png", "image"}:
                return "image"
            return mt or "unknown"
    return "unknown"


def _spike_dates(dates: list[ApproximateDate]) -> list[ApproximateDate]:
    """Dates eligible for activity spikes (plausible diary years only)."""
    return [d for d in dates if is_plausible_diary_year(d.year)]


def _bounds_dates(dates: list[ApproximateDate]) -> list[ApproximateDate]:
    """Dates for notebook start/end labels.

    Plausible years only. When any month/day-precision stamp exists, ignore
    bare years so prose years (e.g. ``1947 change of scenery?``) and folio
    codes do not stretch the card range past real diary stamps.
    """
    dated = _spike_dates(dates)
    precise = [d for d in dated if d.precision != "year"]
    return precise if precise else dated


def _notebook_bounds(
    project: Project,
) -> tuple[ApproximateDate | None, ApproximateDate | None]:
    dated = _bounds_dates([p.date for p in project.pages if p.date is not None])
    derived_start, derived_end = min_date(dated), max_date(dated)
    start = project.date_start if project.date_start is not None else derived_start
    end = project.date_end if project.date_end is not None else derived_end
    if start is not None and not is_plausible_diary_year(start.year):
        start = derived_start
    if end is not None and not is_plausible_diary_year(end.year):
        end = derived_end
    return start, end


def _page_in_period(page_date: ApproximateDate | None, filters: ArchiveFilters) -> bool:
    if page_date is None:
        if filters.period != "all":
            return False
        return filters.include_undated
    if filters.period == "all":
        return True
    if filters.period == "year":
        return filters.year is not None and page_date.year == filters.year
    if filters.range_start is not None and page_date.sort_key() < filters.range_start.sort_key():
        return False
    if filters.range_end is not None and page_date.sort_key() > filters.range_end.sort_key():
        return False
    return True


def _choose_grain(dates: list[ApproximateDate]) -> str:
    if not dates:
        return "month"
    years = sorted({d.year for d in dates})
    span_years = years[-1] - years[0] + 1
    # Long spans: year ticks stay readable; monthly fill would be thousands of bins.
    if span_years >= 8 or len(years) >= 6:
        return "year"
    if len(years) >= 3:
        return "month"
    if len(years) == 1:
        months = {(d.year, d.month or 1) for d in dates}
        return "day" if len(months) <= 2 else "week"
    return "month"


def _period_active(filters: ArchiveFilters) -> bool:
    return filters.period != "all"


def _filters_active_for_notebooks(filters: ArchiveFilters) -> bool:
    return bool(
        _period_active(filters)
        or filters.query
        or filters.tags
        or filters.media_types
        or filters.project_tags
    )


def _fts_match_query(raw: str) -> str | None:
    """Build an FTS5 MATCH expression (AND of quoted tokens), or None if empty."""
    tokens = re.findall(r"[A-Za-z0-9_]+", raw.lower())
    if not tokens:
        return None
    return " AND ".join(f'"{t}"' for t in tokens)


class ArchiveService:
    def __init__(self, runtime: RuntimePaths) -> None:
        self.runtime = runtime
        self.runtime.ensure_layout()
        self.index_path = self.runtime.data_dir / "cache" / "archive.sqlite"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._rebuild_lock_path = self.index_path.with_suffix(".sqlite.lock")
        self._validated_at: float | None = None
        self._validated_generation: int | None = None
        self._ensure_calls = 0  # test counter

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.index_path), timeout=_BUSY_TIMEOUT_MS / 1000.0)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _delete_cache(self) -> None:
        for path in (
            self.index_path,
            Path(str(self.index_path) + "-wal"),
            Path(str(self.index_path) + "-shm"),
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self._validated_at = None
        self._validated_generation = None

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
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
              project_tags_json TEXT NOT NULL DEFAULT '[]',
              text TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES notebooks(project_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id);
            CREATE INDEX IF NOT EXISTS idx_pages_sort ON pages(sort_key);
            """)
        row = conn.execute("SELECT value FROM meta WHERE key = 'cache_schema_version'").fetchone()
        if row is not None:
            cache_version = int(row["value"])
            if cache_version != _CACHE_SCHEMA_VERSION:
                raise sqlite3.DatabaseError(f"incompatible archive cache schema {cache_version}")
        row = conn.execute("SELECT value FROM meta WHERE key = 'fts_schema_version'").fetchone()
        current = int(row["value"]) if row else 0
        if current < _FTS_SCHEMA_VERSION:
            conn.execute("DROP TABLE IF EXISTS pages_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE pages_fts USING fts5(
                  page_id UNINDEXED,
                  project_id UNINDEXED,
                  text,
                  tags,
                  title
                )
                """)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('fts_schema_version', ?)",
                (str(_FTS_SCHEMA_VERSION),),
            )
            # Force full reindex of notebooks by clearing signatures.
            conn.execute("UPDATE notebooks SET signature = ''")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('cache_schema_version', ?)",
            (str(_CACHE_SCHEMA_VERSION),),
        )

    def _project_signature(self, root: Path, project: Project) -> str:
        parts = [project.updated_at, str(len(project.pages))]
        results = root / "results"
        if results.exists():
            mtimes = sorted(f"{p.name}:{p.stat().st_mtime_ns}" for p in results.glob("*.json"))
            parts.extend(mtimes)
        return "|".join(parts)

    def _ttl_fresh(self, *, generation: int, now: float) -> bool:
        return (
            self._validated_at is not None
            and self._validated_generation == generation
            and (now - self._validated_at) < _INDEX_TTL_S
        )

    def ensure_index(self, *, force: bool = False) -> None:
        """Rebuild disposable FTS when forced, TTL expired, or generation bumped.

        The hot-path guard uses an explicit mutation generation token — not
        directory/result mtimes (in-place result edits do not change dir mtime
        reliably). Callers must ``bump_archive_generation`` / ``invalidate``
        after mutations; after TTL expiry a full signature rebuild still runs.
        """
        now = time.monotonic()
        generation = read_archive_generation(self.runtime)
        if not force and self._ttl_fresh(generation=generation, now=now):
            return
        with FileLock(self._rebuild_lock_path, timeout=60.0):
            # Re-check TTL after acquiring the cross-process rebuild lock.
            now = time.monotonic()
            generation = read_archive_generation(self.runtime)
            if not force and self._ttl_fresh(generation=generation, now=now):
                return
            self._ensure_calls += 1
            self._ensure_index_locked(force=force)

    def _ensure_index_locked(self, *, force: bool = False) -> None:
        roots = discover_corpus_project_roots(self.runtime)
        for attempt in range(2):
            try:
                with self._connect() as conn:
                    # Quick corruption probe
                    conn.execute("PRAGMA quick_check").fetchone()
                    self._ensure_schema(conn)
                    # Ensure project_tags_json column exists on older DBs.
                    cols = {r[1] for r in conn.execute("PRAGMA table_info(pages)")}
                    if "project_tags_json" not in cols:
                        conn.execute(
                            "ALTER TABLE pages ADD COLUMN project_tags_json "
                            "TEXT NOT NULL DEFAULT '[]'"
                        )
                    known = {
                        row["project_id"]: (row["signature"], row["root"])
                        for row in conn.execute("SELECT project_id, signature, root FROM notebooks")
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
                        prev = known.get(project.id)
                        # Folder renames keep content signature stable but must
                        # refresh the stored root — stale roots break Open/actions.
                        if (
                            not force
                            and prev is not None
                            and prev[0] == sig
                            and prev[1] == str(root)
                        ):
                            continue
                        self._reindex_project(conn, root, project, projects, sig)
                    stale = set(known) - seen
                    for project_id in stale:
                        conn.execute("DELETE FROM pages_fts WHERE project_id = ?", (project_id,))
                        conn.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
                        conn.execute("DELETE FROM notebooks WHERE project_id = ?", (project_id,))
                    conn.commit()
                self._mark_validated()
                return
            except sqlite3.DatabaseError:
                self._delete_cache()
                if attempt == 1:
                    raise
        self._mark_validated()

    def _mark_validated(self) -> None:
        self._validated_at = time.monotonic()
        self._validated_generation = read_archive_generation(self.runtime)

    def note_mutation(self) -> int:
        """Bump workspace generation and clear in-process TTL (index stays until rebuild)."""
        nxt = bump_archive_generation(self.runtime)
        self._validated_at = None
        self._validated_generation = None
        return nxt

    def invalidate(self, project_id: str) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM pages_fts WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM notebooks WHERE project_id = ?", (project_id,))
            conn.commit()
        self.note_mutation()

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
            page_tags = normalize_tags(page.tags)
            combined_tags = normalize_tags([*project.tags, *page_tags])
            conn.execute(
                """
                INSERT INTO pages(
                  page_id, project_id, page_ord, source_id, media_type,
                  date_json, sort_key, tags_json, project_tags_json, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page.page_id,
                    project.id,
                    ord_i,
                    page.source_id,
                    media,
                    date_json,
                    sort_key,
                    json.dumps(combined_tags),
                    json.dumps(project.tags),
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
                    " ".join(combined_tags),
                    project.title,
                ),
            )

    def _parse_date(self, raw: str | None) -> ApproximateDate | None:
        if not raw:
            return None
        return ApproximateDate.from_dict(json.loads(raw))

    def _load_page_rows(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return list(conn.execute("""
                SELECT p.*, n.title AS project_title, n.root AS project_root,
                       n.page_count AS notebook_page_count,
                       n.date_start_json AS nb_date_start_json,
                       n.date_end_json AS nb_date_end_json,
                       n.tags_json AS notebook_tags_json,
                       n.cover_page_id AS notebook_cover_page_id
                FROM pages p
                JOIN notebooks n ON n.project_id = p.project_id
                """))

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
        # Category toggles are OR: any selected project tag may match.
        if filters.project_tags and not (set(filters.project_tags) & project_tags):
            return False
        q = filters.query.strip().lower()
        if q:
            hay = f"{row['text']} {row['project_title']} {' '.join(tags)}".lower()
            if q not in hay:
                return False
        return True

    def _type_counts_from_rows(
        self, rows: list[sqlite3.Row], base_filters: ArchiveFilters
    ) -> list[TypeCount]:
        """Totals over all rows; selected under base_filters (types unconstrained)."""
        media_totals: dict[str, int] = {}
        media_sel: dict[str, int] = {}
        tag_totals: dict[str, int] = {}
        tag_sel: dict[str, int] = {}
        for row in rows:
            mt = row["media_type"]
            media_totals[mt] = media_totals.get(mt, 0) + 1
            project_tags = json.loads(row["project_tags_json"] or "[]")
            for t in project_tags:
                tag_totals[t] = tag_totals.get(t, 0) + 1
            if self._row_matches(row, base_filters):
                media_sel[mt] = media_sel.get(mt, 0) + 1
                for t in project_tags:
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

    def available_years(self) -> list[int]:
        self.ensure_index()
        with self._connect() as conn:
            years: set[int] = set()
            for row in conn.execute("SELECT date_json FROM pages WHERE date_json IS NOT NULL"):
                d = self._parse_date(row["date_json"])
                if d and is_plausible_diary_year(d.year):
                    years.add(d.year)
            return sorted(years)

    def type_inventory(self, filters: ArchiveFilters | None = None) -> list[TypeCount]:
        self.ensure_index()
        filters = filters or ArchiveFilters()
        # Unconstrain types so selected reflects other active filters only.
        base = ArchiveFilters(
            period=filters.period,
            year=filters.year,
            range_start=filters.range_start,
            range_end=filters.range_end,
            query=filters.query,
            tags=filters.tags,
            notebook_ids=filters.notebook_ids,
            include_undated=filters.include_undated,
        )
        with self._connect() as conn:
            return self._type_counts_from_rows(self._load_page_rows(conn), base)

    def timeline(self, filters: ArchiveFilters | None = None) -> TimelineResult:
        self.ensure_index()
        filters = filters or ArchiveFilters()
        with self._connect() as conn:
            rows = self._load_page_rows(conn)
            total = len(rows)
            matched = [r for r in rows if self._row_matches(r, filters)]
            all_dated: list[ApproximateDate] = []
            undated = 0
            for row in matched:
                d = self._parse_date(row["date_json"])
                if d is None:
                    undated += 1
                else:
                    all_dated.append(d)
            dated_dates = _spike_dates(all_dated)
            grain = _choose_grain(dated_dates)
            counts: dict[str, int] = {}
            for d in dated_dates:
                key = d.bin_key(grain)
                counts[key] = counts.get(key, 0) + 1
            if dated_dates:
                span_start = min_date(dated_dates)
                span_end = max_date(dated_dates)
                assert span_start is not None and span_end is not None
                if filters.period == "year" and filters.year is not None:
                    span_start = ApproximateDate(filters.year, 1, 1)
                    span_end = ApproximateDate(filters.year, 12, 31)
                elif filters.period == "range":
                    if filters.range_start is not None:
                        span_start = filters.range_start
                    if filters.range_end is not None:
                        span_end = filters.range_end
                filled = fill_bin_series(grain, span_start, span_end, counts)
                bins = [TimelineBin(key=k, count=c) for k, c in filled]
            else:
                bins = []
            type_base = ArchiveFilters(
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
                type_counts=self._type_counts_from_rows(rows, type_base),
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
                if _filters_active_for_notebooks(filters):
                    if not matched:
                        continue
                elif filters.notebook_ids and nb["project_id"] not in filters.notebook_ids:
                    continue

                matched_dates = [
                    d for d in (self._parse_date(r["date_json"]) for r in matched) if d is not None
                ]
                dated_only = _spike_dates(matched_dates)
                bounds_dates = _bounds_dates(matched_dates)
                stored_start = self._parse_date(nb["date_start_json"])
                stored_end = self._parse_date(nb["date_end_json"])
                # Prefer stored overrides from reindex (_notebook_bounds already independent).
                # When filters shrink the view, activity uses matched dates; bounds stay notebook-level.
                start = stored_start
                end = stored_end
                if start is not None and not is_plausible_diary_year(start.year):
                    start = None
                if end is not None and not is_plausible_diary_year(end.year):
                    end = None
                if start is None or end is None:
                    d_start, d_end = min_date(bounds_dates), max_date(bounds_dates)
                    if start is None:
                        start = d_start
                    if end is None:
                        end = d_end

                grain = _choose_grain(dated_only) if dated_only else "month"
                activity_counts: dict[str, int] = {}
                for d in dated_only:
                    key = d.bin_key(grain)
                    activity_counts[key] = activity_counts.get(key, 0) + 1
                if dated_only:
                    filled = fill_bin_series(
                        grain,
                        min_date(dated_only),  # type: ignore[arg-type]
                        max_date(dated_only),  # type: ignore[arg-type]
                        activity_counts,
                    )
                    activity = [ActivityBin(key=k, count=c) for k, c in filled]
                else:
                    activity = []
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
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResult:
        self.ensure_index()
        base = filters or ArchiveFilters()
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
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))

        with self._connect() as conn:
            total_indexed = conn.execute("SELECT COUNT(*) AS c FROM pages").fetchone()["c"]
            where: list[str] = ["1=1"]
            params: list[object] = []

            match_expr = _fts_match_query(merged.query) if merged.query.strip() else None
            join_fts = ""
            if match_expr is not None:
                join_fts = "JOIN pages_fts ON pages_fts.page_id = p.page_id"
                where.append("pages_fts MATCH ?")
                params.append(match_expr)

            if merged.notebook_ids:
                placeholders = ",".join("?" * len(merged.notebook_ids))
                where.append(f"p.project_id IN ({placeholders})")
                params.extend(merged.notebook_ids)
            if merged.media_types:
                placeholders = ",".join("?" * len(merged.media_types))
                where.append(f"p.media_type IN ({placeholders})")
                params.extend(merged.media_types)
            if merged.period == "year" and merged.year is not None:
                where.append("p.date_json IS NOT NULL AND p.date_json LIKE ?")
                params.append(f'%"y": {merged.year}%')
                # JSON may be compact without space — also try without space
                # Better: use sort_key range
                where.pop()
                params.pop()
                where.append("p.sort_key IS NOT NULL AND p.sort_key >= ? AND p.sort_key < ?")
                params.append(f"{merged.year:04d}-00-00")
                params.append(f"{merged.year + 1:04d}-00-00")
            elif merged.period == "range":
                where.append("p.sort_key IS NOT NULL")
                if merged.range_start is not None:
                    sk = merged.range_start.sort_key()
                    where.append("p.sort_key >= ?")
                    params.append(f"{sk[0]:04d}-{sk[1]:02d}-{sk[2]:02d}")
                if merged.range_end is not None:
                    sk = merged.range_end.sort_key()
                    where.append("p.sort_key <= ?")
                    params.append(f"{sk[0]:04d}-{sk[1]:02d}-{sk[2]:02d}")
            elif merged.period == "all" and not merged.include_undated:
                where.append("p.sort_key IS NOT NULL")

            # Page tags AND: each required tag must appear in tags_json.
            for tag in merged.tags:
                where.append("p.tags_json LIKE ?")
                params.append(f'%"{tag}"%')

            # Project category tags OR.
            if merged.project_tags:
                ors = " OR ".join("p.project_tags_json LIKE ?" for _ in merged.project_tags)
                where.append(f"({ors})")
                params.extend(f'%"{t}"%' for t in merged.project_tags)

            where_sql = " AND ".join(where)
            order_sql = (
                "p.sort_key DESC NULLS LAST, p.page_ord DESC"
                if order == "newest"
                else "p.sort_key ASC NULLS LAST, p.page_ord ASC"
            )
            # SQLite before 3.30 may lack NULLS LAST — use CASE.
            if order == "newest":
                order_sql = (
                    "CASE WHEN p.sort_key IS NULL THEN 1 ELSE 0 END, "
                    "p.sort_key DESC, p.page_ord DESC"
                )
            else:
                order_sql = (
                    "CASE WHEN p.sort_key IS NULL THEN 1 ELSE 0 END, "
                    "p.sort_key ASC, p.page_ord ASC"
                )

            count_sql = f"""
                SELECT COUNT(*) AS c
                FROM pages p
                JOIN notebooks n ON n.project_id = p.project_id
                {join_fts}
                WHERE {where_sql}
            """
            total_matched = conn.execute(count_sql, params).fetchone()["c"]

            data_sql = f"""
                SELECT p.*, n.title AS project_title, n.root AS project_root,
                       n.page_count AS notebook_page_count
                FROM pages p
                JOIN notebooks n ON n.project_id = p.project_id
                {join_fts}
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
            """
            rows = list(conn.execute(data_sql, [*params, limit, offset]))

            # Fallback: if FTS returned nothing but query looks like a phrase substring,
            # and MATCH was used, also try substring path for OCR quirks.
            if match_expr is not None and total_matched == 0 and merged.query.strip():
                # Substring fallback without FTS join.
                sub = ArchiveFilters(
                    period=merged.period,
                    year=merged.year,
                    range_start=merged.range_start,
                    range_end=merged.range_end,
                    query=merged.query,
                    tags=merged.tags,
                    media_types=merged.media_types,
                    project_tags=merged.project_tags,
                    notebook_ids=merged.notebook_ids,
                    include_undated=merged.include_undated,
                )
                all_rows = self._load_page_rows(conn)
                matched = [r for r in all_rows if self._row_matches(r, sub)]

                def hit_sort_key(row: sqlite3.Row) -> tuple:
                    d = self._parse_date(row["date_json"])
                    key = d.sort_key() if d else (9999, 99, 99)
                    if order == "newest":
                        return (-key[0], -key[1], -key[2], row["page_ord"])
                    return (*key, row["page_ord"])

                matched.sort(key=hit_sort_key)
                total_matched = len(matched)
                rows = matched[offset : offset + limit]

            q = merged.query.strip()
            hits: list[SearchHit] = []
            for row in rows:
                text = row["text"] or ""
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
                        snippet=_snippet(text, q),
                        media_type=row["media_type"],
                    )
                )
            return SearchResult(
                hits=hits,
                showing=len(hits),
                total_matched=total_matched,
                total_indexed=int(total_indexed),
                offset=offset,
                limit=limit,
            )


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
        # try first token
        tok = re.findall(r"[A-Za-z0-9_]+", q)
        if tok:
            idx = lower.find(tok[0])
        if idx < 0:
            return compact[: radius * 2] + ("…" if len(compact) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(compact), idx + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(compact) else ""
    return prefix + compact[start:end] + suffix


def highlight_terms(text: str, query: str) -> str:
    """Return markdown-safe text with query matches wrapped in ``**bold**``."""
    if not text:
        return text
    if not query.strip():
        return escape_markdown_plain(text)
    pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)
    parts: list[str] = []
    last = 0
    for match in pattern.finditer(text):
        parts.append(escape_markdown_plain(text[last : match.start()]))
        parts.append(f"**{escape_markdown_plain(match.group(0))}**")
        last = match.end()
    parts.append(escape_markdown_plain(text[last:]))
    return "".join(parts)
