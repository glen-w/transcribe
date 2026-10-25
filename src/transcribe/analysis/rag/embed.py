"""Ollama embeddings for the notebook RAG index (Paperful nomic prefixes)."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

T = TypeVar("T")

_TASK_PREFIXES: dict[str, tuple[str, str]] = {
    "nomic-embed-text": ("search_document: ", "search_query: "),
}
_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 1.0


class EmbedError(Exception):
    """Configuration or transport error for an embedder."""


class _Retriable(Exception):
    """Transient failure retried by ``_with_retries``."""


def model_base_name(model: str) -> str:
    name = model.strip().lower().rsplit("/", 1)[-1]
    return name.split(":", 1)[0]


def task_prefixes(model: str) -> tuple[str, str]:
    return _TASK_PREFIXES.get(model_base_name(model), ("", ""))


def embed_fingerprint(provider: str, model: str) -> str:
    name = model.strip().lower().removesuffix(":latest")
    slug = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-") or "model"
    return f"{provider.strip().lower()}__{slug}"


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if not norm or not math.isfinite(norm):
        raise EmbedError("embedding model returned an empty or non-finite vector")
    return [x / norm for x in vector]


def _with_retries(
    op: Callable[[], T],
    *,
    attempts: int = _MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(attempts):
        try:
            return op()
        except _Retriable as exc:
            if attempt + 1 >= attempts:
                raise EmbedError(str(exc)) from exc.__cause__
            sleep(_RETRY_BASE_DELAY_S * (2**attempt))
    raise EmbedError("no attempts made")


class Embedder(Protocol):
    provider: str
    model: str
    dim: int | None

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@dataclass
class _BatchingEmbedder:
    model: str
    batch_size: int = 32
    timeout_s: float = 120.0
    dim: int | None = field(default=None, init=False)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        size = max(1, self.batch_size)
        for start in range(0, len(texts), size):
            batch = texts[start : start + size]
            vectors = self._embed_batch(batch)
            if len(vectors) != len(batch):
                raise EmbedError(
                    f"{self.model} returned {len(vectors)} vectors for {len(batch)} texts"
                )
            for vector in vectors:
                if self.dim is None:
                    self.dim = len(vector)
                if len(vector) != self.dim:
                    raise EmbedError(
                        f"{self.model} returned a {len(vector)}-dim vector; "
                        f"expected {self.dim}"
                    )
                out.append(_unit([float(x) for x in vector]))
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefix = task_prefixes(self.model)[0]
        return self._embed([f"{prefix}{text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        prefix = task_prefixes(self.model)[1]
        return self._embed([f"{prefix}{text}"])[0]


@dataclass
class OllamaEmbedder(_BatchingEmbedder):
    base_url: str = "http://127.0.0.1:11434"
    provider: str = "ollama"

    def _api_root(self) -> str:
        return self.base_url.rstrip("/").removesuffix("/v1")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._api_root()}/api/embed"
        payload = json.dumps(
            {"model": self.model, "input": texts, "truncate": True}
        ).encode("utf-8")

        def call() -> list[list[float]]:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
                if exc.code >= 500:
                    raise _Retriable(f"Ollama embedding failed: HTTP {exc.code}") from exc
                if exc.code == 404:
                    raise EmbedError(
                        f"Ollama has no embedding model {self.model!r}. "
                        f"Try: ollama pull {self.model}"
                    ) from exc
                raise EmbedError(
                    f"Ollama embedding failed: HTTP {exc.code} {body[:200]}"
                ) from exc
            except urllib.error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, TimeoutError):
                    raise EmbedError(
                        f"Ollama embedding timed out after {self.timeout_s:g}s"
                    ) from exc
                raise _Retriable(f"Ollama unreachable: {exc.reason}") from exc
            except TimeoutError as exc:
                raise EmbedError(
                    f"Ollama embedding timed out after {self.timeout_s:g}s"
                ) from exc
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError as exc:
                raise EmbedError(f"invalid Ollama embedding response: {exc}") from exc
            vectors = data.get("embeddings") if isinstance(data, dict) else None
            if not isinstance(vectors, list):
                raise EmbedError("Ollama embedding response has no 'embeddings' list")
            return vectors

        return _with_retries(call)


@dataclass
class MemoryEmbedder:
    """Deterministic bag-of-character embedder for offline tests (no Ollama)."""

    model: str = "memory"
    provider: str = "memory"
    dim: int | None = 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vec(text, dim=self.dim or 8) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _hash_vec(text, dim=self.dim or 8)


def _hash_vec(text: str, *, dim: int) -> list[float]:
    vec = [0.0] * dim
    for i, ch in enumerate(text.lower()):
        vec[i % dim] += (ord(ch) % 31) / 31.0
    if not text:
        vec[0] = 1.0
    return _unit(vec)


def embedder_from_rag(
    rag: Any,
    *,
    default_base_url: str,
    embedder: Embedder | None = None,
) -> Embedder:
    if embedder is not None:
        return embedder
    base = str(getattr(rag, "embed_base_url", "") or "").strip() or default_base_url
    return OllamaEmbedder(
        model=str(getattr(rag, "embed_model", "nomic-embed-text")),
        batch_size=int(getattr(rag, "embed_batch_size", 32) or 32),
        base_url=base,
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))
