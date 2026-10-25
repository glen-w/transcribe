"""In-memory chunk index for offline tests (no LanceDB)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.rag.embed import cosine


class MemoryIndex:
    def __init__(self, *, dim: int, meta: dict[str, Any] | None = None):
        self.dim = dim
        self.meta = meta or {"dim": dim}
        self.path = None
        self._rows: list[dict[str, Any]] = []

    def replace_all(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)

    def count(self) -> int:
        return len(self._rows)

    def search(
        self,
        vector: list[float],
        text: str,
        *,
        k: int,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]:
        _ = text, hybrid
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._rows:
            score = cosine(vector, row["vector"])
            hit = {key: row.get(key) for key in row if key != "vector"}
            hit["score"] = float(score)
            scored.append((score, hit))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[:k]]

    def finish(self) -> None:
        return
