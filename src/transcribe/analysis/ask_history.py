"""Ask notebook history — read prior llm_custom_qa attempts for the UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcribe.analysis.storage import AnalysisStorage
from transcribe.persistence.atomic import read_json
from transcribe.ports import to_iso

ASK_MODULE_ID = "llm_custom_qa"
_TERMINAL_ATTEMPT_STATES = frozenset({"succeeded", "failed"})


@dataclass(frozen=True)
class AskHistoryEntry:
    attempt_id: str
    recorded_at: str
    question: str
    model: str
    answer: str | None
    outcome: str
    capability: str
    content_fingerprint: str
    envelope: dict[str, Any]


def _parse_recorded_at(iso: str) -> datetime:
    normalized = iso.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def format_ask_timestamp(iso: str) -> str:
    if not iso:
        return "Unknown date"
    try:
        return _parse_recorded_at(iso).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso[:16]


def _recorded_at_from_path(path: Path) -> str:
    mtime = path.stat().st_mtime
    return to_iso(datetime.fromtimestamp(mtime, tz=timezone.utc))


def _ask_model_name(envelope: dict[str, Any]) -> str:
    payload = envelope.get("payload") or {}
    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    llm = envelope.get("llm") or {}
    model_name = llm.get("model_name")
    if isinstance(model_name, str) and model_name.strip():
        return model_name.strip()
    return ""


def _ask_question_text(envelope: dict[str, Any]) -> str:
    llm = envelope.get("llm") or {}
    question = llm.get("question_text")
    if isinstance(question, str) and question.strip():
        return question.strip()
    payload = envelope.get("payload") or {}
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    return ""


def entry_from_envelope(envelope: dict[str, Any], *, path: Path | None = None) -> AskHistoryEntry | None:
    attempt_id = str(envelope.get("attempt_id") or (path.stem if path else ""))
    if not attempt_id:
        return None
    state = str(envelope.get("attempt_state") or "")
    if state not in _TERMINAL_ATTEMPT_STATES:
        return None
    question = _ask_question_text(envelope)
    if not question:
        return None
    recorded_at = str(envelope.get("recorded_at") or "")
    if not recorded_at and path is not None:
        recorded_at = _recorded_at_from_path(path)
    payload = envelope.get("payload") or {}
    answer = payload.get("answer")
    if answer is not None and not isinstance(answer, str):
        answer = str(answer)
    return AskHistoryEntry(
        attempt_id=attempt_id,
        recorded_at=recorded_at,
        question=question,
        model=_ask_model_name(envelope),
        answer=answer.strip() if isinstance(answer, str) and answer.strip() else None,
        outcome=str(envelope.get("outcome") or ""),
        capability=str(envelope.get("capability") or ""),
        content_fingerprint=str(envelope.get("content_fingerprint") or ""),
        envelope=envelope,
    )


def list_ask_history(storage: AnalysisStorage) -> list[AskHistoryEntry]:
    """All terminal Ask attempts for this notebook, newest first."""
    entries: list[AskHistoryEntry] = []
    for path in storage.iter_attempt_files(ASK_MODULE_ID):
        try:
            envelope = read_json(path)
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(envelope, dict):
            continue
        entry = entry_from_envelope(envelope, path=path)
        if entry is not None:
            entries.append(entry)
    entries.sort(
        key=lambda e: _parse_recorded_at(e.recorded_at) if e.recorded_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return entries


def summarize_ask_label(entry: AskHistoryEntry, *, max_question_chars: int = 72) -> str:
    when = format_ask_timestamp(entry.recorded_at)
    model = entry.model or "unknown model"
    question = entry.question
    if len(question) > max_question_chars:
        question = question[: max_question_chars - 1].rstrip() + "…"
    return f"{when} · {model} · {question}"
