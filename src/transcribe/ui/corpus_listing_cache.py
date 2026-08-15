"""Session-cached corpus listings for Streamlit Batch pickers.

Widget clicks on Analyse / Transcribe Batch must not re-walk every notebook's
page results. Callers pass a cheap ``token`` (see ``corpus_listing_token``) and
optional ``force`` for an explicit Refresh.

Practice rules
--------------
1. Expensive corpus walks (page results, analysis aggregates) go through
   ``get_cached_listing`` + ``corpus_listing_token``, or an explicit Refresh.
2. Mutations that change listings bump ``archive.generation`` *and* invalidate
   the relevant session keys (``invalidate_listing_keys`` /
   ``invalidate_batch_*_caches``).
3. Do not call ``planned_cache_identity`` or bind Ollama from corpus discovery
   / Batch picker paths — use the lightweight scan helpers instead.
4. Prefer ``@st.fragment`` for knob/select panels; prefer targeted session
   invalidation over ``st.cache_resource.clear()`` (which drops live job
   coordinators).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from transcribe.corpus.paths import CorpusPaths

T = TypeVar("T")


def corpus_listing_token(corpus: CorpusPaths) -> str:
    """Cheap invalidation token: archive generation + project.json mtimes."""
    from transcribe.services.archive import discover_project_roots

    gen_path = corpus.data_dir / "cache" / "archive.generation"
    try:
        gen = gen_path.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        gen = "0"
    parts: list[str] = [f"g={gen}"]
    for root in discover_project_roots(corpus.projects_dir):
        try:
            mtime = (root / "project.json").stat().st_mtime_ns
        except OSError:
            mtime = 0
        parts.append(f"{root.name}:{mtime}")
    return "|".join(parts)


def get_cached_listing(
    session_state: Any,
    *,
    cache_key: str,
    token_key: str,
    token: str,
    loader: Callable[[], T],
    force: bool = False,
) -> T:
    """Return a session-cached listing when ``token`` still matches."""
    if (
        not force
        and session_state.get(token_key) == token
        and cache_key in session_state
        and session_state.get(cache_key) is not None
    ):
        cached = session_state[cache_key]
        return list(cached) if isinstance(cached, list) else cached  # type: ignore[return-value]
    value = loader()
    stored = list(value) if isinstance(value, list) else value
    session_state[cache_key] = stored
    session_state[token_key] = token
    return list(stored) if isinstance(stored, list) else stored  # type: ignore[return-value]


def invalidate_listing_keys(session_state: Any, *keys: str) -> None:
    for key in keys:
        session_state.pop(key, None)


def invalidate_listing_key_prefix(session_state: Any, prefix: str) -> None:
    """Drop all session keys that start with ``prefix`` (and matching tokens)."""
    for key in list(session_state.keys()):
        if str(key).startswith(prefix):
            session_state.pop(key, None)
