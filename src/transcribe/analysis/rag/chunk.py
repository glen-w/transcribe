"""Split notebook units into overlapping character passages (Paperful splitter)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from transcribe.analysis.document import AnalysisUnit

CHUNKER_VERSION = 1
MIN_CHUNK_CHARS = 100
_SEPARATORS = ("\n\n", "\n", ". ", " ")
_SENTENCE_START = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass(frozen=True)
class UnitChunk:
    unit_id: str
    page_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    content_fingerprint: str


def chunk_params(*, chunk_chars: int, chunk_overlap: int) -> str:
    overlap = max(0, min(chunk_overlap, chunk_chars // 2))
    return f"c{CHUNKER_VERSION}/{chunk_chars}/{overlap}"


def page_id_of(unit: AnalysisUnit) -> str:
    ref = unit.source_ref or {}
    page_id = ref.get("page_id")
    if isinstance(page_id, str) and page_id.strip():
        return page_id.strip()
    return unit.unit_id.split("/", 1)[0]


def _split(text: str, start: int, end: int, limit: int, depth: int = 0) -> list[tuple[int, int]]:
    if end - start <= limit:
        return [(start, end)]
    if depth >= len(_SEPARATORS):
        return [(s, min(s + limit, end)) for s in range(start, end, limit)]
    sep = _SEPARATORS[depth]
    parts: list[tuple[int, int]] = []
    cursor = start
    while True:
        hit = text.find(sep, cursor, end)
        if hit == -1:
            break
        parts.append((cursor, hit + len(sep)))
        cursor = hit + len(sep)
    if cursor < end:
        parts.append((cursor, end))
    if len(parts) <= 1:
        return _split(text, start, end, limit, depth + 1)
    spans: list[tuple[int, int]] = []
    open_start: int | None = None
    open_end = start
    for part_start, part_end in parts:
        if open_start is not None and part_end - open_start <= limit:
            open_end = part_end
            continue
        if open_start is not None:
            spans.append((open_start, open_end))
            open_start = None
        if part_end - part_start <= limit:
            open_start, open_end = part_start, part_end
        else:
            spans.extend(_split(text, part_start, part_end, limit, depth + 1))
    if open_start is not None:
        spans.append((open_start, open_end))
    return spans


def _overlap_start(text: str, prev_start: int, prev_end: int, overlap: int) -> int:
    if overlap <= 0:
        return prev_end
    begin = max(prev_start, prev_end - overlap)
    if begin == prev_start:
        return begin
    sentence = _SENTENCE_START.search(text, begin, prev_end)
    if sentence:
        return sentence.end()
    space = text.find(" ", begin, prev_end)
    return space + 1 if space != -1 else begin


def chunk_unit(
    unit: AnalysisUnit,
    *,
    chunk_chars: int = 2048,
    overlap: int = 256,
    min_chars: int = MIN_CHUNK_CHARS,
) -> list[UnitChunk]:
    text = unit.text or ""
    if not text.strip():
        return []
    overlap = max(0, min(overlap, chunk_chars // 2))
    limit = max(1, chunk_chars - overlap)
    spans = _split(text, 0, len(text), limit)
    from hashlib import sha256

    chunks: list[UnitChunk] = []
    page_id = page_id_of(unit)
    for i, (span_start, span_end) in enumerate(spans):
        begin = span_start
        if i > 0:
            prev_start, prev_end = spans[i - 1]
            begin = _overlap_start(text, prev_start, prev_end, overlap)
        raw = text[begin:span_end]
        body = raw.strip()
        if len(body) < min_chars and i < len(spans) - 1:
            continue
        if not body:
            continue
        first = begin + (len(raw) - len(raw.lstrip()))
        last = begin + len(raw.rstrip())
        chunks.append(
            UnitChunk(
                unit_id=unit.unit_id,
                page_id=page_id,
                chunk_index=len(chunks),
                text=body,
                char_start=first,
                char_end=last,
                content_fingerprint=sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    if not chunks and text.strip():
        body = text.strip()
        chunks.append(
            UnitChunk(
                unit_id=unit.unit_id,
                page_id=page_id,
                chunk_index=0,
                text=body,
                char_start=0,
                char_end=len(text),
                content_fingerprint=sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def chunk_units(
    units: list[AnalysisUnit],
    *,
    chunk_chars: int = 2048,
    overlap: int = 256,
) -> list[UnitChunk]:
    out: list[UnitChunk] = []
    for unit in units:
        out.extend(chunk_unit(unit, chunk_chars=chunk_chars, overlap=overlap))
    return out
