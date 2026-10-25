"""RAG index / extra errors."""

from __future__ import annotations


class RagUnavailable(Exception):
    """``transcribe[rag]`` (LanceDB) is not installed."""


class IndexMissing(Exception):
    """Nothing has been ingested for the configured embedding model."""


class IndexMismatch(Exception):
    """The index on disk was built with different embedding settings."""
