"""Paperful-shaped RAG ingest (dry-run / skip unchanged / force)."""

from __future__ import annotations

from pathlib import Path

from transcribe.analysis.rag.embed import MemoryEmbedder
from transcribe.analysis.rag.ingest import (
    DONE_EMPTY,
    DONE_INDEXED,
    DONE_UNCHANGED,
    ingest_notebooks,
)
from transcribe.analysis.rag.memory import MemoryIndex
from transcribe.config.models import RagConfig
from transcribe.__main__ import main
from tests.services.test_analysis_wave1e import TEXTS, _project_with_pages


class CountingEmbedder(MemoryEmbedder):
    def __init__(self) -> None:
        self.n_docs = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.n_docs += len(texts)
        return super().embed_documents(texts)


def test_ingest_indexes_then_skips_unchanged(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    embedder = CountingEmbedder()
    rag = RagConfig(enabled=True, hybrid=False)
    batch = ingest_notebooks(
        [projects.paths.root],
        rag=rag,
        embedder=embedder,
        index=MemoryIndex(dim=8),
    )
    assert batch.rows[0].status == DONE_INDEXED
    assert batch.rows[0].chunks >= 1
    first_docs = embedder.n_docs
    assert first_docs >= 1
    again = ingest_notebooks(
        [projects.paths.root],
        rag=rag,
        embedder=embedder,
        index=MemoryIndex(dim=8),
    )
    assert again.rows[0].status == DONE_UNCHANGED
    assert embedder.n_docs == first_docs


def test_ingest_dry_run_writes_nothing(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    embedder = CountingEmbedder()
    rag = RagConfig(enabled=True, hybrid=False)
    batch = ingest_notebooks(
        [projects.paths.root],
        rag=rag,
        dry_run=True,
        embedder=embedder,
        index=MemoryIndex(dim=8),
    )
    assert batch.dry_run
    assert batch.rows[0].status == DONE_INDEXED
    assert embedder.n_docs == 0
    assert not list(projects.paths.rag_dir.glob("**/ingest.jsonl"))


def test_ingest_force_reindexes(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    embedder = CountingEmbedder()
    rag = RagConfig(enabled=True, hybrid=False)
    index = MemoryIndex(dim=8)
    ingest_notebooks([projects.paths.root], rag=rag, embedder=embedder, index=index)
    n = embedder.n_docs
    forced = ingest_notebooks(
        [projects.paths.root],
        rag=rag,
        force=True,
        embedder=embedder,
        index=index,
    )
    assert forced.rows[0].status == DONE_INDEXED
    assert embedder.n_docs > n


def test_ingest_empty_notebook(tmp_path: Path) -> None:
    projects, _ = _project_with_pages(tmp_path, ["   "])
    batch = ingest_notebooks(
        [projects.paths.root],
        rag=RagConfig(enabled=True),
        embedder=MemoryEmbedder(),
        index=MemoryIndex(dim=8),
    )
    assert batch.rows[0].status == DONE_EMPTY


def test_cli_rag_ingest_requires_scope() -> None:
    assert main(["rag", "ingest"]) == 2


def test_cli_rag_ingest_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    projects, _ = _project_with_pages(tmp_path, TEXTS)

    def _fake_ingest(roots, **kwargs):
        from transcribe.analysis.rag.ingest import IngestBatch, IngestRow

        assert kwargs["dry_run"] is True
        assert list(roots) == [projects.paths.root]
        return IngestBatch(
            rows=[IngestRow(projects.load().id, "notebook", DONE_INDEXED, "not indexed yet", 3)],
            dry_run=True,
        )

    monkeypatch.setattr("transcribe.analysis.rag.ingest.ingest_notebooks", _fake_ingest)
    rc = main(["rag", "ingest", str(projects.paths.root), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "indexed=1" in out
    assert "dry-run" in out
