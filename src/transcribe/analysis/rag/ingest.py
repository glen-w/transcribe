"""Build or refresh the per-notebook RAG index from an AnalysisDocument.

Paperful-shaped ``ingest``: skip unchanged notebooks (one ledger read),
``--dry-run`` reports the plan, ``--force`` re-embeds. Transcribe indexes
effective notebook text only — no PDF OCR rewrite, abstracts, or Zotero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from transcribe.analysis.document import AnalysisDocument, AnalysisDocumentError, content_fingerprint
from transcribe.analysis.rag.chunk import chunk_params, chunk_units
from transcribe.analysis.rag.embed import Embedder
from transcribe.analysis.rag.exceptions import IndexMismatch, IndexMissing, RagUnavailable
from transcribe.analysis.rag.index import Index, index_dir, lancedb_available, ledger_path
from transcribe.analysis.rag.ledger import NOTEBOOK_KEY, STATUS_OK, Ledger, LedgerRow, needs_rebuild
from transcribe.config.models import RagConfig

DONE_INDEXED = "indexed"
DONE_UNCHANGED = "unchanged"
DONE_EMPTY = "empty"
DONE_FAILED = "failed"


@dataclass(frozen=True)
class IngestResult:
    rebuilt: bool
    chunks: int
    folder: Path | None
    error: str = ""


@dataclass
class RagRunContext:
    """Runner-supplied RAG I/O (paths + optional test doubles)."""

    rag_root: Path
    force_rebuild: bool = False
    embedder: Embedder | None = None
    index: Any | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"


@dataclass
class IngestRow:
    notebook_id: str
    title: str
    status: str
    reason: str = ""
    chunks: int = 0


@dataclass
class IngestBatch:
    rows: list[IngestRow] = field(default_factory=list)
    dry_run: bool = False

    def count(self, *statuses: str) -> int:
        return sum(1 for row in self.rows if row.status in statuses)

    @property
    def chunks(self) -> int:
        return sum(row.chunks for row in self.rows)

    def summary(self) -> dict[str, int]:
        return {
            "indexed": self.count(DONE_INDEXED),
            "unchanged": self.count(DONE_UNCHANGED),
            "empty": self.count(DONE_EMPTY),
            "failed": self.count(DONE_FAILED),
            "chunks": self.chunks,
        }


def _ask_document(project: Any, project_service: Any) -> AnalysisDocument:
    from transcribe.analysis.adapter import (
        build_page_v1_document,
        build_paragraph_v1_document,
    )

    try:
        return build_paragraph_v1_document(project, project_service)
    except AnalysisDocumentError:
        return build_page_v1_document(project, project_service)


def _plan_status(
    document: AnalysisDocument,
    rag: RagConfig,
    ctx: RagRunContext,
    *,
    force: bool,
    retry_failed: bool,
) -> tuple[str, str, Ledger, Path, str]:
    folder = index_dir(ctx.rag_root, rag.embed_provider, rag.embed_model)
    ledger = Ledger(ledger_path(folder))
    params = chunk_params(chunk_chars=rag.chunk_chars, chunk_overlap=rag.chunk_overlap)
    fp = content_fingerprint(document)
    row = ledger.get(NOTEBOOK_KEY)
    stale = needs_rebuild(
        row, content_fingerprint=fp, params=params, force=force
    )
    if retry_failed and row is not None and (row.status != STATUS_OK or row.error):
        stale = True
    if not document.units or not document.text.strip():
        return DONE_EMPTY, "no transcribed text", ledger, folder, fp
    if not stale:
        return DONE_UNCHANGED, "index is current", ledger, folder, fp
    reason = "forced" if force else "content or chunk settings changed"
    if row is None:
        reason = "not indexed yet"
    return DONE_INDEXED, reason, ledger, folder, fp


def ingest_notebook(
    *,
    project_service: Any,
    rag: RagConfig,
    ctx: RagRunContext,
    force: bool = False,
    retry_failed: bool = False,
    dry_run: bool = False,
) -> IngestRow:
    """Index one notebook's effective text. Embeds only — no Ask LLM call."""
    project = project_service.load()
    title = str(getattr(project, "title", "") or project.id)
    try:
        document = _ask_document(project, project_service)
    except AnalysisDocumentError as exc:
        return IngestRow(project.id, title, DONE_EMPTY, str(exc) or "no transcribed text")

    status, reason, ledger, folder, _fp = _plan_status(
        document, rag, ctx, force=force, retry_failed=retry_failed
    )
    if status in {DONE_EMPTY, DONE_UNCHANGED} or dry_run:
        chunks = 0
        if status == DONE_UNCHANGED:
            row = ledger.get(NOTEBOOK_KEY)
            chunks = int(row.chunks) if row else 0
        elif status == DONE_INDEXED and dry_run:
            chunks = len(
                chunk_units(
                    document.units,
                    chunk_chars=rag.chunk_chars,
                    overlap=rag.chunk_overlap,
                )
            )
        return IngestRow(project.id, title, status, reason, chunks)

    try:
        ctx.force_rebuild = force or retry_failed
        _index, _embedder, result = ensure_index(document, rag, ctx)
    except RagUnavailable as exc:
        return IngestRow(project.id, title, DONE_FAILED, str(exc))
    except (IndexMismatch, IndexMissing, OSError, ValueError) as exc:
        return IngestRow(project.id, title, DONE_FAILED, str(exc))
    if result.error:
        return IngestRow(project.id, title, DONE_FAILED, result.error, result.chunks)
    return IngestRow(
        project.id,
        title,
        DONE_INDEXED,
        reason,
        result.chunks,
    )


def ingest_notebooks(
    roots: Iterable[Path],
    *,
    rag: RagConfig,
    force: bool = False,
    retry_failed: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    embedder: Embedder | None = None,
    index: Any | None = None,
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> IngestBatch:
    """Bring per-notebook indexes in line with ``roots`` (Paperful ``ingest_entries``)."""
    from transcribe.services.project import ProjectService, open_project_paths
    from transcribe.ports import SystemClock, UuidGenerator

    batch = IngestBatch(dry_run=dry_run)
    worked = 0
    clock, ids = SystemClock(), UuidGenerator()
    for root in roots:
        if limit is not None and worked >= limit:
            break
        paths = open_project_paths(root)
        projects = ProjectService(paths, clock=clock, ids=ids)
        ctx = RagRunContext(
            rag_root=paths.rag_dir,
            force_rebuild=force,
            embedder=embedder,
            index=index,
            ollama_base_url=ollama_base_url,
        )
        row = ingest_notebook(
            project_service=projects,
            rag=rag,
            ctx=ctx,
            force=force,
            retry_failed=retry_failed,
            dry_run=dry_run,
        )
        batch.rows.append(row)
        if row.status not in {DONE_UNCHANGED, DONE_EMPTY}:
            worked += 1
    return batch


def ensure_index(
    document: AnalysisDocument,
    rag: RagConfig,
    ctx: RagRunContext,
) -> tuple[Any, Embedder, IngestResult]:
    from transcribe.analysis.rag.embed import embedder_from_rag

    embedder = embedder_from_rag(
        rag, default_base_url=ctx.ollama_base_url, embedder=ctx.embedder
    )
    folder = index_dir(ctx.rag_root, rag.embed_provider, rag.embed_model)
    ledger = Ledger(ledger_path(folder))
    params = chunk_params(chunk_chars=rag.chunk_chars, chunk_overlap=rag.chunk_overlap)
    fp = content_fingerprint(document)
    stale = needs_rebuild(
        ledger.get(NOTEBOOK_KEY),
        content_fingerprint=fp,
        params=params,
        force=ctx.force_rebuild,
    )

    if ctx.index is not None:
        if not stale:
            count = ctx.index.count() if hasattr(ctx.index, "count") else 0
            return ctx.index, embedder, IngestResult(False, count, folder)
        result = _ingest_into(
            document,
            rag,
            index=ctx.index,
            embedder=embedder,
            folder=folder,
            ledger=ledger,
            force=True,
        )
        return ctx.index, embedder, result

    if not lancedb_available():
        raise RagUnavailable("lancedb is not installed; pip install -e '.[rag]'")

    if not stale:
        try:
            index = Index.open(
                ctx.rag_root,
                provider=rag.embed_provider,
                model=rag.embed_model,
            )
            return index, embedder, IngestResult(False, index.count(), folder)
        except (IndexMissing, IndexMismatch):
            stale = True

    probe = embedder.embed_documents(["probe"])
    dim = len(probe[0])
    try:
        index = Index.open(
            ctx.rag_root,
            provider=rag.embed_provider,
            model=rag.embed_model,
            dim=dim,
            create=True,
        )
    except IndexMismatch:
        # Different model folder is the Paperful rule; mismatch inside a folder
        # means delete-and-recreate the table by opening a fresh folder name.
        raise
    result = _ingest_into(
        document,
        rag,
        index=index,
        embedder=embedder,
        folder=folder,
        ledger=ledger,
        force=True,
    )
    return index, embedder, result


def _ingest_into(
    document: AnalysisDocument,
    rag: RagConfig,
    *,
    index: Any,
    embedder: Embedder,
    folder: Path | None,
    ledger: Ledger | None,
    force: bool,
) -> IngestResult:
    _ = force
    chunks = chunk_units(
        document.units,
        chunk_chars=rag.chunk_chars,
        overlap=rag.chunk_overlap,
    )
    texts = [ch.text for ch in chunks]
    vectors = embedder.embed_documents(texts) if texts else []
    rows: list[dict[str, Any]] = []
    for ch, vector in zip(chunks, vectors):
        rows.append(
            {
                "chunk_id": f"{ch.unit_id}#{ch.chunk_index}",
                "unit_id": ch.unit_id,
                "page_id": ch.page_id,
                "chunk_index": ch.chunk_index,
                "text": ch.text,
                "content_fingerprint": ch.content_fingerprint,
                "char_start": ch.char_start,
                "char_end": ch.char_end,
                "vector": vector,
            }
        )
    index.replace_all(rows)
    if hasattr(index, "finish"):
        try:
            index.finish()
        except Exception:  # noqa: BLE001 — hybrid FTS is best-effort
            pass
    if ledger is not None:
        ledger.write(
            LedgerRow(
                key=NOTEBOOK_KEY,
                status=STATUS_OK,
                chunks=len(rows),
                content_fingerprint=content_fingerprint(document),
                params=chunk_params(
                    chunk_chars=rag.chunk_chars, chunk_overlap=rag.chunk_overlap
                ),
            )
        )
    return IngestResult(True, len(rows), folder)
