"""Phase 6 #7 — task-shaped Analyse read-models (no module-console chrome).

Numeric foundations and mood modules compare this notebook to a corpus or
period average (TranscriptX compared speakers; notebooks compare peers).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from transcribe.analysis.health import AnalysisHealth, ModuleHealth
from transcribe.services.analysis_compare import extract_foundations_display
from transcribe.ui.analysis_compare_view import (
    render_compare_period_controls,
    render_module_compare_charts,
)
from transcribe.ui.analysis_health_view import (
    module_may_show_payload,
    product_capability_label,
    render_advanced_payload,
    render_module_unavailable,
)


def _env_payload(mh: ModuleHealth) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    env = mh.envelope or {}
    payload = env.get("payload") if isinstance(env, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    outcome = env.get("outcome") if isinstance(env, dict) else None
    return env if isinstance(env, dict) else {}, payload, str(outcome) if outcome else None


def _show_or_note(mh: ModuleHealth, *, title: str) -> dict[str, Any] | None:
    if not module_may_show_payload(mh):
        render_module_unavailable(mh, product_title=title)
        return None
    _, payload, outcome = _env_payload(mh)
    if outcome == "failed" or mh.capability == "failed":
        render_module_unavailable(mh, product_title=title)
        return None
    if mh.capability in {
        "unavailable_model",
        "unavailable_extra",
        "unavailable_dependency",
    }:
        render_module_unavailable(mh, product_title=title)
        return None
    if outcome in {"insufficient_data", "skipped_not_applicable"}:
        render_module_unavailable(mh, product_title=title)
        return None
    return payload


def render_overview_product(
    health: AnalysisHealth,
    overview_ids: list[str],
    *,
    render_page_metrics: Callable[[], None] | None = None,
    projects_dir: Path | None = None,
    project_id: str | None = None,
) -> None:
    st.subheader("Overview")
    st.caption(
        "Notebook snapshot: counts, diversity, entities, themes, and page ink. "
        "Numeric charts can compare this notebook with the corpus or a selected period."
    )
    if render_page_metrics is not None:
        try:
            render_page_metrics()
            st.divider()
        except Exception:  # noqa: BLE001 — optional surface
            pass

    period = None
    if projects_dir is not None:
        with st.expander("Compare with corpus / period", expanded=False):
            period = render_compare_period_controls(
                key_prefix="overview",
                projects_dir=projects_dir,
            )

    # Stats / diversity / understandability — real payload keys + compare charts
    for mid, title in (
        ("stats", "Counts"),
        ("lexical_diversity", "Lexical diversity"),
        ("understandability", "Understandability"),
    ):
        if mid not in overview_ids:
            continue
        mh = health.modules.get(mid)
        if mh is None:
            continue
        payload = _show_or_note(mh, title=title)
        if payload is None:
            continue
        bits = extract_foundations_display(payload, mid)
        if bits:
            st.markdown(
                f"**{title}** · " + " · ".join(f"{lab}={val}" for lab, val in bits[:8])
            )
        else:
            st.markdown(f"**{title}** · ready")
        if period is not None:
            render_module_compare_charts(
                mid,
                payload,
                projects_dir=projects_dir,
                period=period,
                exclude_project_id=project_id,
                chart_key=f"overview_{mid}",
            )
        elif mid == "lexical_diversity":
            # Standalone visual when no corpus dir (still show this-notebook bars).
            from transcribe.services.analysis_compare import extract_module_metrics

            cur = extract_module_metrics(mid, payload)
            if cur:
                st.bar_chart(
                    {
                        "metric": list(cur.keys()),
                        "value": list(cur.values()),
                    },
                    x="metric",
                    y="value",
                )
        # Per-page token / TTR sparkline when unit rows exist
        units = payload.get("units") if isinstance(payload.get("units"), list) else []
        if mid == "stats" and units:
            st.caption("Tokens per page")
            st.bar_chart(
                {
                    "order": [u.get("order") for u in units if isinstance(u, dict)],
                    "tokens": [
                        int(u.get("token_count") or 0) for u in units if isinstance(u, dict)
                    ],
                },
                x="order",
                y="tokens",
            )
        if mid == "lexical_diversity" and units:
            ttr_series = [
                float(u["ttr"])
                for u in units
                if isinstance(u, dict) and u.get("ttr") is not None
            ]
            if ttr_series:
                st.caption("TTR across pages")
                st.line_chart(
                    {
                        "order": [
                            u.get("order")
                            for u in units
                            if isinstance(u, dict) and u.get("ttr") is not None
                        ],
                        "ttr": ttr_series,
                    },
                    x="order",
                    y="ttr",
                )
        render_advanced_payload(mid, payload)

    if "wordclouds" in overview_ids:
        mh = health.modules.get("wordclouds")
        if mh is not None:
            payload = _show_or_note(mh, title="Word themes")
            if payload is not None:
                tokens = payload.get("tokens") or []
                if isinstance(tokens, list) and tokens:
                    st.markdown("**Word themes**")
                    st.bar_chart(
                        {
                            "token": [t.get("token", "") for t in tokens[:40]],
                            "weight": [float(t.get("weight") or 0) for t in tokens[:40]],
                        },
                        x="token",
                        y="weight",
                    )
                else:
                    st.info("Word themes: no tokens yet.")
                render_advanced_payload("wordclouds", payload)

    if "ner" in overview_ids:
        mh = health.modules.get("ner")
        if mh is not None:
            payload = _show_or_note(mh, title="People & entities")
            if payload is not None:
                counts = payload.get("entity_counts") or {}
                st.markdown("**People & entities**")
                if counts:
                    items = list(counts.items())[:20]
                    st.bar_chart(
                        {
                            "entity": [k for k, _ in items],
                            "count": [int(v) for _, v in items],
                        },
                        x="entity",
                        y="count",
                    )
                else:
                    st.caption("No named entities found.")
                render_advanced_payload("ner", payload)

    if "sentiment" in overview_ids:
        mh = health.modules.get("sentiment")
        if mh is not None:
            payload = _show_or_note(mh, title="Sentiment")
            if payload is not None:
                units = payload.get("units") or []
                st.markdown("**Sentiment over pages**")
                if units:
                    st.line_chart(
                        {
                            "order": [u.get("order") for u in units],
                            "compound": [float(u.get("compound") or 0) for u in units],
                        },
                        x="order",
                        y="compound",
                    )
                gs = payload.get("global_stats") or {}
                if gs.get("compound_mean") is not None:
                    st.caption(f"Mean compound={float(gs['compound_mean']):.3f}")
                if period is not None:
                    render_module_compare_charts(
                        "sentiment",
                        payload,
                        projects_dir=projects_dir,
                        period=period,
                        exclude_project_id=project_id,
                        chart_key="overview_sentiment",
                    )
                render_advanced_payload("sentiment", payload)

    if "epistemic_markers" in overview_ids:
        mh = health.modules.get("epistemic_markers")
        if mh is not None:
            payload = _show_or_note(mh, title="Hedging & certainty")
            if payload is not None:
                g = payload.get("global_stats") or {}
                st.markdown(
                    f"**Hedging & certainty** · hedge "
                    f"{g.get('hedge_share', '—')} · booster "
                    f"{g.get('booster_share', '—')} · hits "
                    f"{g.get('total_marker_hits', '—')}"
                )
                if period is not None:
                    render_module_compare_charts(
                        "epistemic_markers",
                        payload,
                        projects_dir=projects_dir,
                        period=period,
                        exclude_project_id=project_id,
                        chart_key="overview_epistemic",
                    )
                render_advanced_payload("epistemic_markers", payload)

    # Any remaining overview modules not specially rendered
    handled = {
        "stats",
        "lexical_diversity",
        "understandability",
        "wordclouds",
        "ner",
        "sentiment",
        "epistemic_markers",
    }
    for mid in overview_ids:
        if mid in handled:
            continue
        mh = health.modules.get(mid)
        if mh is None:
            continue
        payload = _show_or_note(mh, title=mid.replace("_", " ").title())
        if payload is not None:
            st.markdown(f"**{mid.replace('_', ' ').title()}** · ready")
            render_advanced_payload(mid, payload)


def render_themes_product(health: AnalysisHealth, theme_ids: list[str]) -> None:
    st.subheader("Themes")
    st.caption(
        "Topics, keyphrases, and how themes shift across the notebook. "
        "Run analysis from the preset form above."
    )
    titles = {
        "keyphrases": "Keyphrases",
        "topic_modeling": "Topics",
        "semantic_similarity": "Similar passages",
        "topic_shift": "Theme shifts",
        "bertopic": "BERTopic clusters",
    }
    for mid in theme_ids:
        mh = health.modules[mid]
        title = titles.get(mid, mid.replace("_", " ").title())
        payload = _show_or_note(mh, title=title)
        if payload is None:
            continue
        if mid == "keyphrases" and payload.get("phrases"):
            st.markdown("**Keyphrases**")
            phrases = payload["phrases"][:12]
            st.write(
                ", ".join(p.get("phrase", "") for p in phrases if p.get("phrase"))
            )
            # Weight bars when scores exist
            scored = [
                p
                for p in phrases
                if isinstance(p, dict) and p.get("phrase") and p.get("score") is not None
            ]
            if scored:
                st.bar_chart(
                    {
                        "phrase": [p["phrase"][:40] for p in scored],
                        "score": [float(p["score"]) for p in scored],
                    },
                    x="phrase",
                    y="score",
                )
        elif mid == "topic_modeling" and payload.get("topics"):
            st.markdown("**Topics**")
            for topic in payload["topics"][:5]:
                terms = ", ".join(topic.get("terms") or [])
                st.write(f"- **{topic.get('label')}**: {terms}")
        elif mid == "semantic_similarity":
            motifs = payload.get("motifs") or []
            st.markdown(
                f"**Similar passages** · {payload.get('n_units', 0)} units · "
                f"{len(motifs)} motif pair(s)"
            )
            if motifs:
                top = motifs[:8]
                st.bar_chart(
                    {
                        "pair": [
                            f"{m.get('unit_id_a', '?')}↔{m.get('unit_id_b', '?')}"[:28]
                            for m in top
                        ],
                        "similarity": [float(m.get("similarity") or 0) for m in top],
                    },
                    x="pair",
                    y="similarity",
                )
        elif mid == "topic_shift":
            shifts = payload.get("shifts") or []
            consecutive = payload.get("consecutive") or []
            st.markdown(
                f"**Theme shifts** · {payload.get('n_units', 0)} units · "
                f"{len(shifts)} boundary(ies)"
            )
            if consecutive:
                st.caption("Adjacent-page similarity (drops mark theme shifts)")
                st.line_chart(
                    {
                        "order": [c.get("from_order") for c in consecutive],
                        "similarity": [
                            float(c.get("similarity") or 0) for c in consecutive
                        ],
                    },
                    x="order",
                    y="similarity",
                )
            if shifts:
                for sh in shifts[:8]:
                    st.write(
                        f"- after order {sh.get('order_after')} "
                        f"(sim={sh.get('similarity')})"
                    )
        elif mid == "bertopic":
            topics = payload.get("topics") or payload.get("clusters") or []
            st.markdown(
                f"**BERTopic clusters** · "
                f"{product_capability_label(mh.capability, mh.outcome)}"
            )
            if isinstance(topics, list) and topics:
                for topic in topics[:6]:
                    if isinstance(topic, dict):
                        terms = ", ".join(
                            topic.get("terms") or topic.get("words") or []
                        )
                        st.write(f"- **{topic.get('label') or topic.get('topic_id')}**: {terms}")
        else:
            st.markdown(f"**{title}** · ready")
        render_advanced_payload(mid, payload)


def render_mood_product(
    health: AnalysisHealth,
    mood_ids: list[str],
    *,
    projects_dir: Path | None = None,
    project_id: str | None = None,
) -> None:
    st.subheader("Mood & tone")
    st.caption(
        "Emotion, affect tension, and hedging across the notebook. "
        "Compare intensity / polarity with the corpus or a selected period."
    )
    period = None
    if projects_dir is not None:
        with st.expander("Compare with corpus / period", expanded=False):
            period = render_compare_period_controls(
                key_prefix="mood",
                projects_dir=projects_dir,
            )
    titles = {
        "sentiment": "Sentiment",
        "emotion": "Emotion",
        "contextual_emotion": "Contextual emotion",
        "fine_grained_emotion": "Fine-grained emotion",
        "affect_tension": "Affect tension",
        "epistemic_markers": "Hedging & certainty",
    }
    for mid in mood_ids:
        mh = health.modules[mid]
        title = titles.get(mid, mid.replace("_", " ").title())
        payload = _show_or_note(mh, title=title)
        if payload is None:
            continue
        units = payload.get("units") if isinstance(payload.get("units"), list) else []
        if mid == "sentiment":
            gs = payload.get("global_stats") or {}
            st.markdown(
                f"**Sentiment** · mean {gs.get('compound_mean', '—')}"
            )
            if units:
                st.line_chart(
                    {
                        "order": [u.get("order") for u in units],
                        "compound": [float(u.get("compound") or 0) for u in units],
                    },
                    x="order",
                    y="compound",
                )
        elif mid == "emotion":
            gs = payload.get("global_stats") or {}
            st.markdown(
                f"**Emotion** · intensity mean "
                f"{gs.get('intensity_mean', '—')}"
            )
            if units and any(u.get("intensity") is not None for u in units if isinstance(u, dict)):
                st.line_chart(
                    {
                        "order": [u.get("order") for u in units],
                        "intensity": [float(u.get("intensity") or 0) for u in units],
                    },
                    x="order",
                    y="intensity",
                )
        elif mid == "affect_tension":
            gs = payload.get("global_stats") or {}
            st.markdown(
                f"**Affect tension** · mean {gs.get('tension_mean', '—')} · "
                f"conflicts {gs.get('n_conflicting', '—')}"
            )
            if units and any(u.get("tension") is not None for u in units if isinstance(u, dict)):
                st.line_chart(
                    {
                        "order": [u.get("order") for u in units],
                        "tension": [float(u.get("tension") or 0) for u in units],
                    },
                    x="order",
                    y="tension",
                )
        elif mid == "epistemic_markers":
            g = payload.get("global_stats") or {}
            st.markdown(
                f"**Hedging & certainty** · hedge {g.get('hedge_share', '—')} · "
                f"booster {g.get('booster_share', '—')}"
            )
            if units:
                hedge_vals = []
                boost_vals = []
                orders = []
                for u in units:
                    if not isinstance(u, dict):
                        continue
                    counts = u.get("category_counts") or {}
                    if not isinstance(counts, dict):
                        counts = {}
                    orders.append(u.get("order"))
                    hedge_vals.append(
                        int(counts.get("epistemic_hedge") or 0)
                        + int(counts.get("approximator") or 0)
                        + int(counts.get("modal_uncertainty") or 0)
                    )
                    boost_vals.append(int(counts.get("certainty_booster") or 0))
                if orders:
                    st.bar_chart(
                        {
                            "order": orders,
                            "hedges": hedge_vals,
                            "boosters": boost_vals,
                        },
                        x="order",
                        y=["hedges", "boosters"],
                    )
        elif mid in {"contextual_emotion", "fine_grained_emotion"}:
            gs = payload.get("global_stats") or {}
            label = gs.get("top_label") or gs.get("dominant_label")
            intensity = gs.get("intensity_mean")
            if label or intensity is not None:
                st.markdown(
                    f"**{title}** · "
                    + " · ".join(
                        x
                        for x in (
                            f"top={label}" if label else None,
                            f"intensity={intensity}" if intensity is not None else None,
                        )
                        if x
                    )
                )
            else:
                st.markdown(f"**{title}** · ready")
            if units and any(
                isinstance(u, dict) and u.get("intensity") is not None for u in units
            ):
                st.line_chart(
                    {
                        "order": [u.get("order") for u in units],
                        "intensity": [float(u.get("intensity") or 0) for u in units],
                    },
                    x="order",
                    y="intensity",
                )
        else:
            st.markdown(f"**{title}** · ready")

        if period is not None and mid in {
            "sentiment",
            "emotion",
            "affect_tension",
            "epistemic_markers",
        }:
            render_module_compare_charts(
                mid,
                payload,
                projects_dir=projects_dir,
                period=period,
                exclude_project_id=project_id,
                chart_key=f"mood_{mid}",
            )
        render_advanced_payload(mid, payload)


def render_moments_product(
    health: AnalysisHealth,
    *,
    on_jump: Callable[[str], None] | None = None,
) -> None:
    st.subheader("Moments")
    st.caption(
        "Salient quotes from the notebook. Run analysis from the preset form above."
    )
    mh = health.modules["moments"]
    payload = _show_or_note(mh, title="Moments")
    if payload is None:
        return
    moments = payload.get("moments") or []
    if not moments:
        st.info("No salient moments found yet.")
        render_advanced_payload("moments", payload)
        return
    for row in moments:
        quote = (row.get("quote") or "")[:200]
        score = row.get("score")
        page_id = row.get("page_id") or row.get("unit_id")
        line = f"- {quote}"
        if score is not None:
            line = f"- _{score}_ · {quote}"
        st.markdown(line)
        if on_jump and page_id and st.button(
            "Jump to page",
            key=f"moment_jump_{page_id}_{hash(quote) & 0xFFFF}",
        ):
            on_jump(str(page_id))
    env = mh.envelope or {}
    for w in env.get("warnings") or []:
        st.caption(w.get("message") or w.get("code"))
    render_advanced_payload("moments", payload)


def render_summaries_product(health: AnalysisHealth, synth_ids: list[str]) -> None:
    st.subheader("Summaries")
    st.caption(
        "Highlights, summary, and insights. Optional LLM outputs appear when a "
        "text model is available. Run analysis from the preset form above."
    )
    titles = {
        "topic_modeling": "Topics (context)",
        "highlights": "Highlights",
        "summary": "Summary",
        "insights": "Insights",
        "llm_summary": "LLM summary",
        "llm_action_items": "Action items",
        "narrative_summary": "Narrative summary",
    }
    for mid in synth_ids:
        mh = health.modules[mid]
        title = titles.get(mid, mid.replace("_", " ").title())
        payload = _show_or_note(mh, title=title)
        if payload is None:
            continue
        honesty = payload.get("honesty_label")
        st.markdown(f"**{title}**")
        if honesty:
            st.caption(honesty)

        if mid == "highlights":
            quotes = payload.get("quotes") or []
            if quotes:
                for q in quotes[:12]:
                    if isinstance(q, dict):
                        text = q.get("text") or ""
                        score = q.get("score")
                        prefix = f"_{score}_ · " if score is not None else ""
                        st.write(f"- {prefix}{text[:300]}")
            else:
                st.caption("No highlight quotes yet.")
        elif mid == "summary":
            overview = payload.get("overview") or payload.get("summary") or payload.get("text")
            bullets = payload.get("bullets") or []
            if overview:
                st.markdown(str(overview))
            if isinstance(bullets, list) and bullets:
                for b in bullets[:12]:
                    st.write(f"- {b}")
            if not overview and not bullets:
                st.caption("Ready — open Advanced for details.")
        elif mid == "insights":
            themes = payload.get("themes") or []
            notable = payload.get("notable_quotes") or []
            if themes:
                st.markdown("Themes")
                for t in themes[:8]:
                    if isinstance(t, dict):
                        terms = ", ".join(t.get("terms") or [])
                        st.write(f"- **{t.get('label')}**: {terms}")
            if notable:
                st.markdown("Notable quotes")
                for q in notable[:6]:
                    if isinstance(q, dict):
                        st.write(f"- {q.get('text') or ''}")
            if not themes and not notable:
                st.caption("Ready — open Advanced for details.")
        elif mid == "topic_modeling" and payload.get("topics"):
            for topic in payload["topics"][:5]:
                terms = ", ".join(topic.get("terms") or [])
                st.write(f"- **{topic.get('label')}**: {terms}")
        else:
            text = (
                payload.get("summary")
                or payload.get("text")
                or payload.get("narrative")
                or payload.get("answer")
            )
            items = (
                payload.get("highlights")
                or payload.get("insights")
                or payload.get("items")
            )
            if text:
                st.markdown(str(text))
            elif isinstance(items, list) and items:
                for it in items[:12]:
                    if isinstance(it, dict):
                        st.write(f"- {it.get('text') or it.get('highlight') or it}")
                    else:
                        st.write(f"- {it}")
            else:
                st.caption("Ready — open Advanced for details.")
        if mh.live_evidence:
            st.caption(f"{len(mh.live_evidence)} supporting citation(s)")
        render_advanced_payload(mid, payload)


def render_ask_product(
    *,
    runner: Any,
    question_key: str = "ask_notebook_question",
) -> None:
    st.subheader("Ask notebook")
    st.caption(
        "Ask a question grounded in this notebook. Unsupported answers abstain — "
        "no fabricated citations. Ad-hoc Ask does not update batch analysis health."
    )
    question = st.text_input("Question", key=question_key)
    if st.button("Ask", disabled=not (question or "").strip()):
        with st.spinner("Asking notebook…"):
            env = runner.run_module("llm_custom_qa", question_text=question.strip())
        payload = env.get("payload") or {}
        if payload.get("honesty_label"):
            st.caption(payload["honesty_label"])
        if env.get("outcome") == "failed" or env.get("capability") in {
            "unavailable_model",
            "unavailable_dependency",
            "failed",
        }:
            st.warning(
                product_capability_label(
                    env.get("capability"), env.get("outcome")
                )
            )
        if payload.get("answer"):
            st.markdown(payload["answer"])
        evidence = env.get("evidence") or []
        from transcribe.analysis.envelope import filter_live_evidence

        live = filter_live_evidence(
            evidence,
            current_content_fingerprint=env.get("content_fingerprint"),
        )
        if live and env.get("published"):
            with st.expander("Supporting passages"):
                for cite in live:
                    st.write(cite)
        elif evidence and env.get("published"):
            st.caption("Evidence citations omitted (content changed since Ask).")
        for w in env.get("warnings") or []:
            st.warning(w.get("message") or w.get("code"))
        render_advanced_payload("ask", payload)
