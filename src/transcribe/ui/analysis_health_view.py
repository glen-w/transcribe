"""Shared Analyse health presentation (Phase 4 + Phase 6 product language)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from transcribe.analysis.health import AnalysisHealth, ModuleHealth

# Product-facing copy for capability / outcome enums (Phase 6 #7).
_CAPABILITY_COPY: dict[str, str] = {
    "unavailable_model": "Needs a text model",
    "unavailable_extra": "Optional component not installed",
    "unavailable_dependency": "Waiting on another result",
    "insufficient_data": "Not enough text yet",
    "skipped_not_applicable": "Not applicable for this notebook",
    "partial": "Partial result",
    "failed": "Failed",
    "success": "Ready",
}

_AGGREGATE_COPY: dict[str, str] = {
    "healthy": "Healthy",
    "degraded": "Degraded",
    "stale": "Out of date",
    "missing": "Not run yet",
    "failed": "Failed",
    "running": "Running",
    "interrupted": "Interrupted",
}


def product_capability_label(capability: str | None, outcome: str | None = None) -> str:
    """Map capability/outcome enums to ordinary-user language."""
    if capability and capability in _CAPABILITY_COPY:
        return _CAPABILITY_COPY[capability]
    if outcome and outcome in _CAPABILITY_COPY:
        return _CAPABILITY_COPY[outcome]
    if outcome == "success":
        return "Ready"
    if capability:
        return capability.replace("_", " ")
    if outcome:
        return outcome.replace("_", " ")
    return "Unavailable"


def product_aggregate_label(aggregate: str) -> str:
    return _AGGREGATE_COPY.get(aggregate, aggregate.replace("_", " ").title())


def render_status_strip(
    health: AnalysisHealth,
    *,
    ask_note: bool = False,
) -> None:
    """Sole default freshness/health answer above Analyse result tabs (#8)."""
    rev = health.content_revision[:12] if health.content_revision else "?"
    label = product_aggregate_label(health.aggregate)
    parts = [f"Notebook revision `{rev}…`", f"**{label}**"]
    if health.active_run_status == "running":
        parts.append("run in progress")
    elif health.active_run_status == "interrupted":
        parts.append("last run interrupted")
    st.info(" · ".join(parts))
    if ask_note:
        st.caption("Ask notebook is ad-hoc and does not update batch analysis health.")


def render_aggregate_caption(health: AnalysisHealth) -> None:
    """Back-compat one-line caption (prefer :func:`render_status_strip` for default chrome)."""
    rev = health.content_revision[:12] if health.content_revision else "?"
    st.caption(
        f"Notebook revision `{rev}…` · batch health "
        f"**{product_aggregate_label(health.aggregate)}**"
    )


def module_may_show_payload(mh: ModuleHealth) -> bool:
    """True when a published, non-stale envelope may drive a product view."""
    if mh.freshness == "unavailable" or mh.envelope is None:
        return False
    if mh.freshness == "stale":
        return False
    return True


def render_module_unavailable(mh: ModuleHealth, *, product_title: str | None = None) -> None:
    """Single empty/unavailable line in product language (no module-id chrome)."""
    title = product_title or "This section"
    if mh.freshness == "stale":
        st.warning(f"{title} is out of date — refresh analysis.")
        return
    if mh.freshness == "unavailable" or mh.envelope is None:
        st.info(f"{title}: run analysis to see results.")
        return
    label = product_capability_label(mh.capability, mh.outcome)
    if mh.outcome == "failed" or mh.capability == "failed":
        st.error(f"{title}: {label}.")
    elif mh.capability in {
        "unavailable_model",
        "unavailable_extra",
        "unavailable_dependency",
    }:
        st.warning(f"{title}: {label}.")
    else:
        st.info(f"{title}: {label}.")


def render_module_health_banner(mh: ModuleHealth, *, style: str = "default") -> bool:
    """Legacy banner — prefer product views + status strip. Still used by Places.

    Returns True when payload may be shown. Uses product language (Phase 6).
    """
    title = mh.module_id
    if mh.freshness == "unavailable" or mh.envelope is None:
        if style == "overview":
            st.warning(f"**{title}:** unavailable (no validated published result)")
        else:
            st.info(f"**{title}:** run analysis first")
        return False
    if mh.freshness == "stale":
        st.warning(f"**{title}:** out of date — refresh analysis")
        return False

    label = product_capability_label(mh.capability, mh.outcome)
    honesty = None
    if isinstance(mh.envelope, dict):
        honesty = (mh.envelope.get("payload") or {}).get("honesty_label")

    if style == "overview":
        if mh.outcome == "failed":
            st.error(f"**{title}:** {label}")
        elif mh.capability in {
            "unavailable_extra",
            "unavailable_model",
            "unavailable_dependency",
        }:
            st.warning(f"**{title}:** {label}")
        elif mh.outcome in {"insufficient_data", "skipped_not_applicable"}:
            st.info(f"**{title}:** {label}")
        elif mh.capability == "partial":
            st.success(f"**{title}:** {label}")
        else:
            st.success(f"**{title}:** {label}")
        return True

    banner = f"**{title}:** {label}"
    if honesty:
        banner += f" — _{honesty}_"
    if mh.capability in {"unavailable_extra", "unavailable_model", "unavailable_dependency"}:
        st.warning(banner)
    elif mh.capability in {"insufficient_data", "skipped_not_applicable"} or mh.outcome in {
        "insufficient_data",
        "skipped_not_applicable",
    }:
        st.info(banner)
    elif mh.outcome == "failed" or mh.capability == "failed":
        st.error(banner)
    else:
        st.caption(banner)
    return True


def render_advanced_payload(label: str, payload: Any) -> None:
    """Technical details expander — not on the default path."""
    with st.expander(f"Advanced · {label}"):
        st.json(payload)


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


def last_run_product_summary(
    last: dict[str, Any],
    *,
    preset_label: str | None = None,
) -> str:
    """Short product summary for Last run (#7)."""
    n = len(last)
    ok = sum(1 for v in last.values() if v.get("outcome") == "success")
    failed = sum(
        1
        for v in last.values()
        if v.get("outcome") == "failed" or v.get("capability") == "failed"
    )
    if failed:
        health = "issues"
    elif ok == n and n:
        health = "healthy"
    elif ok:
        health = "partial"
    else:
        health = "no successes"
    head = preset_label or "Last run"
    return f"{head} · {n} module{'s' if n != 1 else ''} · {health}"
