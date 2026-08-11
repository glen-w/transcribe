"""Phase 6 #7 — task-shaped Analyse read-models (no module-console chrome)."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from transcribe.analysis.health import AnalysisHealth, ModuleHealth
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
) -> None:
    st.subheader("Overview")
    st.caption(
        "Notebook snapshot: counts, diversity, entities, themes, and page ink. "
        "Run analysis from the preset form above."
    )
    if render_page_metrics is not None:
        try:
            render_page_metrics()
            st.divider()
        except Exception:  # noqa: BLE001 — optional surface
            pass

    # Stats / diversity / understandability as caption chips when present
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
        bits: list[str] = []
        for key in (
            "n_pages",
            "n_words",
            "n_chars",
            "type_token_ratio",
            "flesch_reading_ease",
            "avg_sentence_length",
        ):
            if key in payload and payload[key] is not None:
                bits.append(f"{key.replace('_', ' ')}={payload[key]}")
        if bits:
            st.markdown(f"**{title}** · " + " · ".join(bits[:8]))
        else:
            st.markdown(f"**{title}** · ready")
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
            st.write(
                ", ".join(
                    p.get("phrase", "") for p in payload["phrases"][:12] if p.get("phrase")
                )
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
        elif mid == "topic_shift":
            shifts = payload.get("shifts") or []
            st.markdown(
                f"**Theme shifts** · {payload.get('n_units', 0)} units · "
                f"{len(shifts)} boundary(ies)"
            )
        elif mid == "bertopic":
            st.markdown(f"**BERTopic clusters** · {product_capability_label(mh.capability, mh.outcome)}")
        else:
            st.markdown(f"**{title}** · ready")
        render_advanced_payload(mid, payload)


def render_mood_product(health: AnalysisHealth, mood_ids: list[str]) -> None:
    st.subheader("Mood & tone")
    st.caption(
        "Emotion, affect tension, and hedging across the notebook. "
        "Run analysis from the preset form above."
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
        if mid == "emotion" and payload.get("global_stats"):
            st.markdown(
                f"**Emotion** · intensity mean "
                f"{payload['global_stats'].get('intensity_mean', '—')}"
            )
        elif mid == "affect_tension" and payload.get("global_stats"):
            gs = payload["global_stats"]
            st.markdown(
                f"**Affect tension** · mean {gs.get('tension_mean', '—')} · "
                f"conflicts {gs.get('n_conflicting', '—')}"
            )
        elif mid == "epistemic_markers" and payload.get("global_stats"):
            g = payload["global_stats"]
            st.markdown(
                f"**Hedging & certainty** · hedge {g.get('hedge_share', '—')} · "
                f"booster {g.get('booster_share', '—')}"
            )
        else:
            st.markdown(f"**{title}** · ready")
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
        # Prefer human-readable fields when present
        text = (
            payload.get("summary")
            or payload.get("text")
            or payload.get("narrative")
            or payload.get("answer")
        )
        items = payload.get("highlights") or payload.get("insights") or payload.get("items")
        honesty = payload.get("honesty_label")
        st.markdown(f"**{title}**")
        if honesty:
            st.caption(honesty)
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
