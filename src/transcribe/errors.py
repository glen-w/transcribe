"""Typed application errors."""

from __future__ import annotations


class TranscribeError(Exception):
    """Base error."""


class IngestError(TranscribeError):
    retriable = False


class ProviderError(TranscribeError):
    def __init__(self, message: str, *, retriable: bool = False, code: str = "provider_error"):
        super().__init__(message)
        self.retriable = retriable
        self.code = code


class ProjectError(TranscribeError):
    pass


class ValidationError(ProjectError):
    """Persisted model or on-disk integrity failed validation."""


class JobConflictError(TranscribeError):
    pass
