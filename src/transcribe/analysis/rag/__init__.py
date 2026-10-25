"""Opt-in Ask RAG (Paperful-shaped index + retrieve)."""

from __future__ import annotations

from transcribe.analysis.rag.embed import (
    EmbedError,
    Embedder,
    MemoryEmbedder,
    OllamaEmbedder,
    embed_fingerprint,
    task_prefixes,
)
from transcribe.analysis.rag.exceptions import IndexMismatch, IndexMissing, RagUnavailable
from transcribe.analysis.rag.retrieve import Hit, search_hits

__all__ = [
    "EmbedError",
    "Embedder",
    "Hit",
    "IndexMismatch",
    "IndexMissing",
    "MemoryEmbedder",
    "OllamaEmbedder",
    "RagUnavailable",
    "embed_fingerprint",
    "search_hits",
    "task_prefixes",
]
