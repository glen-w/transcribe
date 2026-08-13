"""Phase 6 #7 — task-shaped Analyse read-models (no module-console chrome).

Each module gets a product visual suited to its payload (metrics, series,
ranked lists, quote cards). Numeric foundations and mood modules can also
compare this notebook to a corpus or period average (TX speaker-bar analogue).
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
from transcribe.ui.analysis_display_helpers import (
    ACTION_TYPE_LABELS,
    aggregate_entity_sentiment,
    contextual_label_counts,
    emotion_label_totals,
    epistemic_category_bars,
    group_action_items,
    moments_score_rows,
    motif_rows,
    ranked_dict,
    sentiment_bucket_counts,
    topic_weight_rows,
    unit_series,
)
from transcribe.ui.analysis_health_view import (
    module_may_show_payload,
    product_capability_label,
    render_advanced_payload,
    render_module_unavailable,
)
from transcribe.ui.wordcloud_render import render_wordcloud_section


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


def _bar_pairs(pairs: list[tuple[str, float]], *, x_name: str, y_name: str) -> None:
    if not pairs:
        return
    st.bar_chart(
        {x_name: [k for k, _ in pairs], y_name: [v for _, v in pairs]},
        x=x_name,
        y=y_name,
    )


def _maybe_compare(
    module_id: str,
    payload: dict[str, Any],
    *,
    period: Any,
    projects_dir: Path | None,
    project_id: str | None,
    chart_key: str,
) -> None:
    if period is None or projects_dir is None:
        return
    render_module_compare_charts(
        module_id,
        payload,
        projects_dir=projects_dir,
        period=period,
        exclude_project_id=project_id,
        chart_key=chart_key,
    )


def render_entity_sentiment_section(payload: dict[str, Any]) -> None:
    """People & places polish: entity × polarity (not corpus-comparable)."""
    rows = aggregate_entity_sentiment(payload, limit=24)
    if not rows:
        st.caption("No entity–sentiment joins yet.")
        return
    st.markdown("#### Entity tone")
    st.caption(
        "Named entities joined to the page’s sentiment (this notebook only — "
        "not compared across the corpus)."
    )
    chart_rows = [r for r in rows if r["mentions"] >= 1][:16]
    st.bar_chart(
        {
            "entity": [r["entity"][:28] for r in chart_rows],
            "mean sentiment": [r["mean_sentiment"] for r in chart_rows],
        },
        x="entity",
        y="mean sentiment",
    )
    st.dataframe(
        [
            {
                "entity": r["entity"],
                "type": r["label"],
                "mentions": r["mentions"],
                "mean": r["mean_sentiment"],
                "polarity": r["polarity"],
            }
            for r in rows
        ],
        width="stretch",
        hide_index=True,
    )


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
        _maybe_compare(
            mid,
            payload,
            period=period,
            projects_dir=projects_dir,
            project_id=project_id,
            chart_key=f"overview_{mid}",
        )
        units = payload.get("units") if isinstance(payload.get("units"), list) else []
        if mid == "stats" and units:
            orders, tokens = unit_series(units, "token_count")
            if orders:
                st.caption("Tokens per page")
                st.bar_chart({"order": orders, "tokens": tokens}, x="order", y="tokens")
        if mid == "lexical_diversity" and units:
            orders, ttrs = unit_series(units, "ttr")
            if orders:
                st.caption("TTR across pages")
                st.line_chart({"order": orders, "ttr": ttrs}, x="order", y="ttr")
        if mid == "understandability" and units:
            orders, flesch = unit_series(units, "flesch_reading_ease")
            if orders:
                st.caption("Flesch reading ease across pages")
                st.line_chart(
                    {"order": orders, "flesch": flesch}, x="order", y="flesch"
                )
        render_advanced_payload(mid, payload)

    if "wordclouds" in overview_ids:
        mh = health.modules.get("wordclouds")
        if mh is not None:
            payload = _show_or_note(mh, title="Word themes")
            if payload is not None:
                st.markdown("**Word themes**")
                render_wordcloud_section(payload, key_prefix="overview_wc")
                render_advanced_payload("wordclouds", payload)

    if "ner" in overview_ids:
        mh = health.modules.get("ner")
        if mh is not None:
            payload = _show_or_note(mh, title="People & entities")
            if payload is not None:
                st.markdown("**People & entities**")
                label_rows = ranked_dict(payload.get("label_counts"), limit=12)
                if label_rows:
                    st.caption("By entity type")
                    _bar_pairs(label_rows, x_name="type", y_name="count")
                entity_rows = ranked_dict(payload.get("entity_counts"), limit=20)
                if entity_rows:
                    st.caption("Top surfaces")
                    _bar_pairs(entity_rows, x_name="entity", y_name="count")
                if not label_rows and not entity_rows:
                    st.caption("No named entities found.")
                render_advanced_payload("ner", payload)

    if "sentiment" in overview_ids:
        mh = health.modules.get("sentiment")
        if mh is not None:
            payload = _show_or_note(mh, title="Sentiment")
            if payload is not None:
                units = payload.get("units") or []
                st.markdown("**Sentiment over pages**")
                orders, compounds = unit_series(units, "compound")
                if orders:
                    st.line_chart(
                        {"order": orders, "compound": compounds},
                        x="order",
                        y="compound",
                    )
                buckets = sentiment_bucket_counts(payload)
                if buckets:
                    st.caption("Tone mix")
                    _bar_pairs(buckets, x_name="tone", y_name="pages")
                gs = payload.get("global_stats") or {}
                if gs.get("compound_mean") is not None:
                    st.caption(f"Mean compound={float(gs['compound_mean']):.3f}")
                _maybe_compare(
                    "sentiment",
                    payload,
                    period=period,
                    projects_dir=projects_dir,
                    project_id=project_id,
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
                cats = epistemic_category_bars(payload)
                if cats:
                    st.caption("Marker categories")
                    _bar_pairs(cats, x_name="category", y_name="hits")
                _maybe_compare(
                    "epistemic_markers",
                    payload,
                    period=period,
                    projects_dir=projects_dir,
                    project_id=project_id,
                    chart_key="overview_epistemic",
                )
                render_advanced_payload("epistemic_markers", payload)

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
        "These are structural views of this notebook (not corpus averages)."
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
            phrases = [p for p in payload["phrases"] if isinstance(p, dict)][:16]
            st.write(
                ", ".join(p.get("phrase", "") for p in phrases if p.get("phrase"))
            )
            scored = [
                p for p in phrases if p.get("phrase") and p.get("score") is not None
            ]
            if scored:
                st.bar_chart(
                    {
                        "phrase": [str(p["phrase"])[:40] for p in scored],
                        "score": [float(p["score"]) for p in scored],
                    },
                    x="phrase",
                    y="score",
                )
        elif mid == "topic_modeling":
            rows = topic_weight_rows(payload, limit=8)
            st.markdown("**Topics**")
            if rows:
                st.bar_chart(
                    {
                        "topic": [r["label"][:32] for r in rows],
                        "pages": [r["weight"] for r in rows],
                    },
                    x="topic",
                    y="pages",
                )
                for r in rows:
                    terms = ", ".join(r["terms"])
                    st.write(f"- **{r['label']}**: {terms}")
            else:
                st.caption("No topics yet.")
        elif mid == "semantic_similarity":
            motifs = motif_rows(payload, limit=10)
            st.markdown(
                f"**Similar passages** · {payload.get('n_units', 0)} units · "
                f"{len(payload.get('motifs') or [])} motif pair(s)"
            )
            if motifs:
                st.bar_chart(
                    {
                        "pair": [m["pair_label"] for m in motifs],
                        "similarity": [m["similarity"] for m in motifs],
                    },
                    x="pair",
                    y="similarity",
                )
                for m in motifs[:6]:
                    st.write(
                        f"- `{m['unit_id_a']}` ↔ `{m['unit_id_b']}` · "
                        f"sim={m['similarity']:.3f}"
                    )
            else:
                st.caption("No similar pairs above the threshold.")
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
            rows = topic_weight_rows(payload, limit=8)
            st.markdown(
                f"**BERTopic clusters** · "
                f"{product_capability_label(mh.capability, mh.outcome)}"
            )
            if rows:
                st.bar_chart(
                    {
                        "cluster": [r["label"][:32] for r in rows],
                        "weight": [r["weight"] for r in rows],
                    },
                    x="cluster",
                    y="weight",
                )
                for r in rows:
                    st.write(f"- **{r['label']}**: {', '.join(r['terms'])}")
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
        "Intensity / polarity can compare with the corpus or a selected period."
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
            st.markdown(f"**Sentiment** · mean {gs.get('compound_mean', '—')}")
            orders, compounds = unit_series(units, "compound")
            if orders:
                st.line_chart(
                    {"order": orders, "compound": compounds},
                    x="order",
                    y="compound",
                )
            buckets = sentiment_bucket_counts(payload)
            if buckets:
                st.caption("Tone mix")
                _bar_pairs(buckets, x_name="tone", y_name="pages")
        elif mid == "emotion":
            gs = payload.get("global_stats") or {}
            st.markdown(
                f"**Emotion** · intensity mean {gs.get('intensity_mean', '—')}"
            )
            labels = emotion_label_totals(payload)
            if labels:
                st.caption("Emotion lexicon totals")
                _bar_pairs(labels, x_name="emotion", y_name="weight")
            orders, intensities = unit_series(units, "intensity")
            if orders:
                st.caption("Intensity across pages")
                st.line_chart(
                    {"order": orders, "intensity": intensities},
                    x="order",
                    y="intensity",
                )
        elif mid == "affect_tension":
            gs = payload.get("global_stats") or {}
            st.markdown(
                f"**Affect tension** · mean {gs.get('tension_mean', '—')} · "
                f"conflicts {gs.get('n_conflicting', '—')}"
            )
            orders, tensions = unit_series(units, "tension")
            if orders:
                st.line_chart(
                    {"order": orders, "tension": tensions},
                    x="order",
                    y="tension",
                )
        elif mid == "epistemic_markers":
            g = payload.get("global_stats") or {}
            st.markdown(
                f"**Hedging & certainty** · hedge {g.get('hedge_share', '—')} · "
                f"booster {g.get('booster_share', '—')}"
            )
            cats = epistemic_category_bars(payload)
            if cats:
                _bar_pairs(cats, x_name="category", y_name="hits")
            hedge_vals: list[int] = []
            boost_vals: list[int] = []
            orders_ep: list[Any] = []
            for u in units:
                if not isinstance(u, dict):
                    continue
                counts = u.get("category_counts") or {}
                if not isinstance(counts, dict):
                    counts = {}
                orders_ep.append(u.get("order"))
                hedge_vals.append(
                    int(counts.get("epistemic_hedge") or 0)
                    + int(counts.get("approximator") or 0)
                    + int(counts.get("modal_uncertainty") or 0)
                )
                boost_vals.append(int(counts.get("certainty_booster") or 0))
            if orders_ep:
                st.caption("Hedges vs boosters by page")
                st.bar_chart(
                    {
                        "order": orders_ep,
                        "hedges": hedge_vals,
                        "boosters": boost_vals,
                    },
                    x="order",
                    y=["hedges", "boosters"],
                )
        elif mid == "contextual_emotion":
            label_counts = contextual_label_counts(payload)
            orders, intensities = unit_series(units, "intensity")
            top = label_counts[0][0] if label_counts else None
            mean_i = (
                sum(intensities) / len(intensities) if intensities else None
            )
            bits = []
            if top:
                bits.append(f"dominant={top}")
            if mean_i is not None:
                bits.append(f"intensity={mean_i:.3f}")
            st.markdown(
                f"**{title}** · " + (" · ".join(bits) if bits else "neighbour-window blend")
            )
            if label_counts:
                st.caption("Top emotion by page (neighbour-smoothed)")
                _bar_pairs(label_counts, x_name="emotion", y_name="pages")
            if orders:
                st.line_chart(
                    {"order": orders, "intensity": intensities},
                    x="order",
                    y="intensity",
                )
        elif mid == "fine_grained_emotion":
            # Optional extra — when a real payload appears, reuse emotion visuals.
            labels = emotion_label_totals(payload) or contextual_label_counts(payload)
            orders, intensities = unit_series(units, "intensity")
            st.markdown(f"**{title}**")
            if labels:
                _bar_pairs(labels, x_name="emotion", y_name="weight")
            if orders:
                st.line_chart(
                    {"order": orders, "intensity": intensities},
                    x="order",
                    y="intensity",
                )
            if not labels and not orders:
                st.caption("Ready — open Advanced for details.")
        else:
            st.markdown(f"**{title}** · ready")

        if mid in {
            "sentiment",
            "emotion",
            "affect_tension",
            "epistemic_markers",
        }:
            _maybe_compare(
                mid,
                payload,
                period=period,
                projects_dir=projects_dir,
                project_id=project_id,
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
    rows = moments_score_rows(payload, limit=16)
    if not rows:
        st.info("No salient moments found yet.")
        render_advanced_payload("moments", payload)
        return
    st.bar_chart(
        {
            "moment": [r["moment"][:36] for r in rows],
            "score": [r["score"] for r in rows],
        },
        x="moment",
        y="score",
    )
    for row in rows:
        quote = (row.get("quote") or "")[:240]
        st.markdown(f"- _{row['score']:.3g}_ · {quote}")
        page_id = row.get("unit_id")
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
                scored = [
                    q
                    for q in quotes
                    if isinstance(q, dict) and q.get("score") is not None
                ]
                if scored:
                    st.bar_chart(
                        {
                            "quote": [
                                (q.get("text") or "")[:36] for q in scored[:12]
                            ],
                            "score": [float(q["score"]) for q in scored[:12]],
                        },
                        x="quote",
                        y="score",
                    )
                for q in quotes[:12]:
                    if isinstance(q, dict):
                        text = q.get("text") or ""
                        score = q.get("score")
                        prefix = f"_{score}_ · " if score is not None else ""
                        st.write(f"- {prefix}{text[:300]}")
            else:
                st.caption("No highlight quotes yet.")
        elif mid == "summary":
            overview = (
                payload.get("overview")
                or payload.get("summary")
                or payload.get("text")
            )
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
        elif mid == "topic_modeling":
            rows = topic_weight_rows(payload, limit=6)
            if rows:
                st.bar_chart(
                    {
                        "topic": [r["label"][:32] for r in rows],
                        "pages": [r["weight"] for r in rows],
                    },
                    x="topic",
                    y="pages",
                )
                for r in rows:
                    st.write(f"- **{r['label']}**: {', '.join(r['terms'])}")
            else:
                st.caption("No topics yet.")
        elif mid == "llm_action_items":
            groups = group_action_items(payload)
            if groups:
                for rtype, texts in groups.items():
                    st.markdown(f"**{ACTION_TYPE_LABELS.get(rtype, rtype)}**")
                    for text in texts[:12]:
                        st.write(f"- {text}")
            else:
                st.caption("No action items extracted.")
        elif mid == "llm_summary":
            text = payload.get("summary") or payload.get("text")
            bullets = payload.get("bullets") or []
            if text:
                st.markdown(str(text))
            if isinstance(bullets, list):
                for b in bullets[:12]:
                    st.write(f"- {b}")
            if not text and not bullets:
                st.caption("Ready — open Advanced for details.")
        elif mid == "narrative_summary":
            text = payload.get("narrative") or payload.get("summary") or payload.get("text")
            if text:
                st.markdown(str(text))
            else:
                st.caption("Ready — open Advanced for details.")
        else:
            text = (
                payload.get("summary")
                or payload.get("text")
                or payload.get("narrative")
                or payload.get("answer")
            )
            items = payload.get("items")
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
