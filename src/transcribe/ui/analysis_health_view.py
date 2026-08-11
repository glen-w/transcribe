"""Shared Analyse health presentation helpers (Phase 4)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcribe.analysis.health import AnalysisHealth, ModuleHealth


def render_aggregate_caption(health: AnalysisHealth) -> None:
    """One-line shared answer to 'is this current and healthy?'."""
    rev = health.content_revision[:12] if health.content_revision else "?"
    st.caption(
        f"Notebook revision `{rev}…` · batch health **{health.aggregate}**"
    )


def render_module_health_banner(mh: ModuleHealth, *, style: str = "default") -> bool:
    """Render freshness/capability banner. Returns True when payload may be shown."""
    mid = mh.module_id
    if mh.freshness == "unavailable" or mh.envelope is None:
        if style == "overview":
            st.warning(f"**{mid}:** unavailable (no validated published result)")
        else:
            st.info(f"**{mid}:** unavailable — run analysis first")
        return False
    if mh.freshness == "stale":
        outcome = mh.outcome or "?"
        st.warning(
            f"**{mid}:** stale relative to current notebook — refresh analysis "
            f"(last outcome `{outcome}`)"
        )
        return False

    env = mh.envelope
    cap = mh.capability
    outcome = mh.outcome
    if style == "overview":
        if outcome == "failed":
            st.error(f"**{mid}:** failed")
        elif outcome == "insufficient_data":
            st.info(f"**{mid}:** insufficient_data")
        elif cap in {"unavailable_extra", "unavailable_model"}:
            st.warning(f"**{mid}:** {cap}")
        elif cap == "partial":
            st.success(f"**{mid}:** success (partial)")
        else:
            st.success(f"**{mid}:** success ({cap})")
        return True

    banner = f"**{mid}:** capability=`{cap}` outcome=`{outcome}`"
    honesty = (env.get("payload") or {}).get("honesty_label") if isinstance(env, dict) else None
    if honesty:
        banner += f" — _{honesty}_"
    if cap == "unavailable_extra":
        st.warning(banner + " (optional extra not available)")
    elif cap == "unavailable_dependency":
        st.warning(banner + " (unavailable dependency)")
    elif cap == "unavailable_model":
        st.warning(banner + " (LLM offline)")
    elif cap in {"insufficient_data", "skipped_not_applicable"}:
        st.info(banner)
    elif outcome == "failed" or cap == "failed":
        st.error(banner)
    else:
        st.markdown(banner)
    return True


def module_health_map(health: AnalysisHealth) -> dict[str, ModuleHealth]:
    return dict(health.modules)


def read_model_compat(mh: ModuleHealth) -> dict[str, Any]:
    """Shape compatible with prior per-tab module_freshness dicts."""
    return {
        "status": mh.freshness,
        "module_id": mh.module_id,
        "envelope": mh.envelope,
        "live_evidence": list(mh.live_evidence),
    }
