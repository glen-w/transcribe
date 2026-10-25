"""LanceDB notebook chunk index (Paperful table shape, unit/page columns)."""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from transcribe.analysis.rag.embed import embed_fingerprint, task_prefixes
from transcribe.analysis.rag.exceptions import IndexMismatch, IndexMissing, RagUnavailable
from transcribe.persistence.atomic import read_json, write_json_atomic

META_SCHEMA = "transcribe.rag.index.v1"
INDEX_VERSION = 1
TABLE = "chunks"
_COLUMNS = (
    "chunk_id",
    "unit_id",
    "page_id",
    "chunk_index",
    "text",
    "content_fingerprint",
    "char_start",
    "char_end",
)


def lancedb_available() -> bool:
    try:
        import lancedb  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _lancedb() -> Any:
    try:
        import lancedb
    except ImportError as exc:
        raise RagUnavailable(
            "lancedb is not installed; pip install -e '.[rag]'"
        ) from exc
    return lancedb


def index_dir(rag_root: Path, provider: str, model: str) -> Path:
    return rag_root / embed_fingerprint(provider, model)


def ledger_path(folder: Path) -> Path:
    return folder / "ingest.jsonl"


def meta_path(folder: Path) -> Path:
    return folder / "meta.json"


def expected_meta(*, provider: str, model: str, dim: int) -> dict[str, Any]:
    doc_prefix, query_prefix = task_prefixes(model)
    return {
        "schema": META_SCHEMA,
        "index_version": INDEX_VERSION,
        "provider": provider,
        "model": model.strip(),
        "dim": dim,
        "doc_prefix": doc_prefix,
        "query_prefix": query_prefix,
    }


def load_meta(folder: Path) -> dict[str, Any] | None:
    path = meta_path(folder)
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


class Index:
    def __init__(self, table: Any, meta: dict[str, Any], path: Path):
        self._table = table
        self.meta = meta
        self.path = path

    @property
    def dim(self) -> int:
        return int(self.meta["dim"])

    @classmethod
    def open(
        cls,
        rag_root: Path,
        *,
        provider: str,
        model: str,
        dim: int | None = None,
        create: bool = False,
    ) -> Index:
        lancedb = _lancedb()
        folder = index_dir(rag_root, provider, model)
        meta = load_meta(folder)
        if meta is None:
            if not create:
                raise IndexMissing(f"no RAG index for {model!r} yet")
            if dim is None:
                raise ValueError("dim is required to create an index")
            meta = {**expected_meta(provider=provider, model=model, dim=dim), "created": time.time()}
            folder.mkdir(parents=True, exist_ok=True)
            write_json_atomic(meta_path(folder), meta)
        want = expected_meta(
            provider=provider, model=model, dim=int(meta.get("dim") or 0)
        )
        if dim is not None:
            want["dim"] = dim
        for name, value in want.items():
            if meta.get(name) != value:
                raise IndexMismatch(
                    f"index at {folder} has {name} = {meta.get(name)!r}, "
                    f"but the configuration gives {value!r}. Rebuild the index."
                )
        db = lancedb.connect(str(folder / "lancedb"))
        table_names = _table_names(db)
        if TABLE in table_names:
            table = db.open_table(TABLE)
        elif create:
            table = db.create_table(TABLE, schema=_schema(int(meta["dim"])))
        else:
            raise IndexMissing(f"no RAG index for {model!r} yet")
        return cls(table, meta, folder)

    def replace_all(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if len(row["vector"]) != self.dim:
                raise IndexMismatch(
                    f"embedding has {len(row['vector'])} dimensions; "
                    f"the index holds {self.dim}"
                )
        if self.count() > 0:
            self._table.delete("true")
        if rows:
            self._table.add(rows)

    def count(self) -> int:
        return int(self._table.count_rows())

    def search(
        self,
        vector: list[float],
        text: str,
        *,
        k: int,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]:
        if hybrid and text.strip():
            try:
                query = self._table.search(query_type="hybrid").vector(vector).text(text)
                rows = query.limit(k).to_list()
                return [_hit(row, row.get("_relevance_score")) for row in rows]
            except Exception:  # noqa: BLE001
                pass
        query = self._table.search(vector)
        rows = query.limit(k).to_list()
        return [_hit(row, 1.0 - float(row.get("_distance") or 0.0) / 2.0) for row in rows]

    def finish(self) -> None:
        from lancedb.index import FTS

        if self.count() == 0:
            return
        if not any(
            getattr(index, "index_type", "") == "FTS"
            for index in self._table.list_indices()
        ):
            self._table.create_index("text", config=FTS())
        self._table.optimize(cleanup_older_than=timedelta(0))


def _table_names(db: Any) -> list[str]:
    if hasattr(db, "list_tables"):
        names = db.list_tables()
        return list(names.tables if hasattr(names, "tables") else names)
    names = db.table_names()
    return list(names.tables if hasattr(names, "tables") else names)


def _hit(row: dict[str, Any], score: Any) -> dict[str, Any]:
    hit = {name: row.get(name) for name in _COLUMNS}
    hit["score"] = float(score or 0.0)
    return hit


def _schema(dim: int) -> Any:
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("unit_id", pa.string()),
            pa.field("page_id", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("content_fingerprint", pa.string()),
            pa.field("char_start", pa.int32()),
            pa.field("char_end", pa.int32()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )
