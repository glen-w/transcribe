"""Empty-state taxonomy (TranscriptX-shaped; at most two nav CTAs)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import streamlit as st

EmptyKind = Literal[
    "missing_prerequisite",
    "no_results_yet",
    "filtered_to_zero",
    "error_degraded",
]


@dataclass(frozen=True)
class EmptyCta:
    label: str
    on_click: Callable[[], None]
    key: str
    primary: bool = True


def render_empty_state(
    *,
    kind: EmptyKind,
    title: str,
    body: str,
    primary: EmptyCta | None = None,
    secondary: EmptyCta | None = None,
) -> None:
    """Render a compact empty panel. At most two CTAs."""
    _ = kind  # taxonomy is for callers / tests; chrome is the same.
    st.markdown(f"**{title}**")
    st.caption(body)
    ctas = [c for c in (primary, secondary) if c is not None][:2]
    if not ctas:
        return
    cols = st.columns(len(ctas), gap="small")
    for col, cta in zip(cols, ctas):
        with col:
            if st.button(
                cta.label,
                key=cta.key,
                type="primary" if cta.primary else "secondary",
                width="stretch",
            ):
                cta.on_click()
