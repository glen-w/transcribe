"""Pure helpers that turn analysis payloads into chart/table-ready rows.

Kept Streamlit-free so unit tests can assert meaningful product shapes without UI.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

_ANALYSE_PICKER_STATUS = {
    "missing": "no analysis",
    "degraded": "existing degraded analysis",
    "failed": "existing failed analysis",
    "stale": "existing out-of-date analysis",
    "healthy": "existing analysis",
    "interrupted": "interrupted analysis",
    "running": "analysis running",
}


def analyse_picker_status_phrase(analysis_aggregate: str) -> str:
    """Ordinary-language status for Analyse → Batch pick labels."""
    key = (analysis_aggregate or "").strip() or "missing"
    if key in _ANALYSE_PICKER_STATUS:
        return _ANALYSE_PICKER_STATUS[key]
    return key.replace("_", " ")


def format_analyse_picker_label(title: str, analysis_aggregate: str) -> str:
    """``{title} ({status})`` for the Pick notebooks multiselect."""
    name = (title or "").strip() or "Untitled"
    return f"{name} ({analyse_picker_status_phrase(analysis_aggregate)})"


def unit_series(
    units: list[Any],
    field: str,
    *,
    order_key: str = "order",
) -> tuple[list[Any], list[float]]:
    """Return (orders, values) for units that have ``field``."""
    orders: list[Any] = []
    values: list[float] = []
    for u in units:
        if not isinstance(u, dict) or u.get(field) is None:
            continue
        try:
            values.append(float(u[field]))
        except (TypeError, ValueError):
            continue
        orders.append(u.get(order_key))
    return orders, values


def unit_series_rows(
    units: list[Any],
    field: str,
    *,
    order_key: str = "order",
) -> list[dict[str, Any]]:
    """Return chart rows with ``order``, ``page_id``, and ``field`` value."""
    from transcribe.ui.page_series_selection import page_id_from_unit_id

    out: list[dict[str, Any]] = []
    for u in units:
        if not isinstance(u, dict) or u.get(field) is None:
            continue
        try:
            value = float(u[field])
        except (TypeError, ValueError):
            continue
        raw_page = u.get("page_id")
        page_id = (
            str(raw_page)
            if isinstance(raw_page, str) and raw_page
            else page_id_from_unit_id(
                str(u["unit_id"]) if isinstance(u.get("unit_id"), str) else None
            )
        )
        if not page_id:
            continue
        out.append(
            {
                "order": u.get(order_key),
                "page_id": page_id,
                field: value,
            }
        )
    return out


def topic_shift_series_rows(consecutive: list[Any]) -> list[dict[str, Any]]:
    """Rows for adjacent-page similarity charts (``from_order`` / ``from_unit_id``)."""
    from transcribe.ui.page_series_selection import page_id_from_unit_id

    out: list[dict[str, Any]] = []
    for c in consecutive:
        if not isinstance(c, dict):
            continue
        try:
            sim = float(c.get("similarity") or 0)
        except (TypeError, ValueError):
            continue
        page_id = page_id_from_unit_id(
            str(c["from_unit_id"]) if isinstance(c.get("from_unit_id"), str) else None
        )
        if not page_id or c.get("from_order") is None:
            continue
        out.append(
            {
                "order": c.get("from_order"),
                "page_id": page_id,
                "similarity": sim,
            }
        )
    return out


def epistemic_page_series_rows(units: list[Any]) -> list[dict[str, Any]]:
    """Hedges vs boosters by page for clickable bar charts."""
    from transcribe.ui.page_series_selection import page_id_from_unit_id

    out: list[dict[str, Any]] = []
    for u in units:
        if not isinstance(u, dict):
            continue
        counts = u.get("category_counts") or {}
        if not isinstance(counts, dict):
            counts = {}
        raw_page = u.get("page_id")
        page_id = (
            str(raw_page)
            if isinstance(raw_page, str) and raw_page
            else page_id_from_unit_id(
                str(u["unit_id"]) if isinstance(u.get("unit_id"), str) else None
            )
        )
        if not page_id or u.get("order") is None:
            continue
        out.append(
            {
                "order": u.get("order"),
                "page_id": page_id,
                "hedges": (
                    int(counts.get("epistemic_hedge") or 0)
                    + int(counts.get("approximator") or 0)
                    + int(counts.get("modal_uncertainty") or 0)
                ),
                "boosters": int(counts.get("certainty_booster") or 0),
            }
        )
    return out


def ranked_dict(items: dict[str, Any] | None, *, limit: int = 20) -> list[tuple[str, float]]:
    if not isinstance(items, dict) or not items:
        return []
    rows: list[tuple[str, float]] = []
    for key, raw in items.items():
        try:
            rows.append((str(key), float(raw)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows[:limit]


def wordcloud_rows(payload: dict[str, Any], *, limit: int = 40) -> list[dict[str, Any]]:
    tokens = payload.get("tokens") or []
    out: list[dict[str, Any]] = []
    for t in tokens:
        if not isinstance(t, dict) or not t.get("token"):
            continue
        out.append(
            {
                "token": str(t["token"]),
                "weight": float(t.get("weight") or 0),
                "count": int(t.get("count") or 0),
            }
        )
        if len(out) >= limit:
            break
    return out


def topic_weight_rows(payload: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    topics = payload.get("topics") or []
    rows: list[dict[str, Any]] = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        label = str(t.get("label") or t.get("topic_id") or "topic")
        terms = [str(x) for x in (t.get("terms") or t.get("words") or []) if x][:6]
        try:
            weight = float(
                t.get("weight") if t.get("weight") is not None else len(t.get("unit_ids") or [])
            )
        except (TypeError, ValueError):
            weight = 0.0
        rows.append({"label": label, "terms": terms, "weight": weight})
    rows.sort(key=lambda r: (-r["weight"], r["label"]))
    return rows[:limit]


def motif_rows(payload: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    motifs = payload.get("motifs") or []
    rows: list[dict[str, Any]] = []
    for m in motifs:
        if not isinstance(m, dict):
            continue
        try:
            sim = float(m.get("similarity") or 0)
        except (TypeError, ValueError):
            continue
        a = str(m.get("unit_id_a") or "?")
        b = str(m.get("unit_id_b") or "?")
        rows.append(
            {
                "pair_label": f"{a} ↔ {b}"[:36],
                "unit_id_a": a,
                "unit_id_b": b,
                "similarity": sim,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def emotion_label_totals(payload: dict[str, Any], *, limit: int = 12) -> list[tuple[str, float]]:
    gs = payload.get("global_stats") if isinstance(payload.get("global_stats"), dict) else {}
    totals = gs.get("label_totals") if isinstance(gs, dict) else None
    return ranked_dict(totals if isinstance(totals, dict) else None, limit=limit)


def contextual_label_counts(payload: dict[str, Any], *, limit: int = 12) -> list[tuple[str, float]]:
    """Aggregate unit top_label frequencies when global_stats is absent."""
    units = payload.get("units") or []
    counts: Counter[str] = Counter()
    for u in units:
        if isinstance(u, dict) and u.get("top_label"):
            counts[str(u["top_label"])] += 1
    return ranked_dict(dict(counts), limit=limit)


def sentiment_bucket_counts(payload: dict[str, Any]) -> list[tuple[str, float]]:
    gs = payload.get("global_stats") if isinstance(payload.get("global_stats"), dict) else {}
    dist = gs.get("sentiment_distribution") if isinstance(gs, dict) else None
    if isinstance(dist, dict) and dist:
        return ranked_dict(dist, limit=6)
    units = payload.get("units") or []
    counts: Counter[str] = Counter()
    for u in units:
        if isinstance(u, dict) and u.get("label"):
            counts[str(u["label"])] += 1
    return ranked_dict(dict(counts), limit=6)


def epistemic_category_bars(payload: dict[str, Any], *, limit: int = 8) -> list[tuple[str, float]]:
    gs = payload.get("global_stats") if isinstance(payload.get("global_stats"), dict) else {}
    counts = gs.get("category_counts") if isinstance(gs, dict) else None
    return ranked_dict(counts if isinstance(counts, dict) else None, limit=limit)


def aggregate_entity_sentiment(
    payload: dict[str, Any],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Roll entity mentions up by surface text for a polarity table/chart."""
    entities = payload.get("entities") or []
    buckets: dict[str, dict[str, Any]] = {}
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        text = (ent.get("text") or "").strip()
        if not text:
            continue
        sent = ent.get("sentiment") if isinstance(ent.get("sentiment"), dict) else {}
        compound = sent.get("compound")
        label = sent.get("label") or "neutral"
        key = text.casefold()
        row = buckets.get(key)
        if row is None:
            row = {
                "text": text,
                "ner_label": ent.get("label") or "",
                "mentions": 0,
                "compounds": [],
                "labels": Counter(),
            }
            buckets[key] = row
        row["mentions"] += 1
        if compound is not None:
            try:
                row["compounds"].append(float(compound))
            except (TypeError, ValueError):
                pass
        row["labels"][str(label)] += 1
    out: list[dict[str, Any]] = []
    for row in buckets.values():
        compounds = row["compounds"]
        mean = sum(compounds) / len(compounds) if compounds else 0.0
        top_polarity = "neutral"
        if row["labels"]:
            top_polarity = row["labels"].most_common(1)[0][0]
        out.append(
            {
                "entity": row["text"],
                "label": row["ner_label"],
                "mentions": row["mentions"],
                "mean_sentiment": round(mean, 4),
                "polarity": top_polarity,
            }
        )
    out.sort(key=lambda r: (-r["mentions"], r["entity"].casefold()))
    return out[:limit]


def group_action_items(payload: dict[str, Any]) -> dict[str, list[str]]:
    items = payload.get("items") or []
    groups: dict[str, list[str]] = defaultdict(list)
    order = ("action_item", "decision", "open_question")
    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or "").strip()
        if not text:
            continue
        rtype = str(it.get("record_type") or "action_item")
        if rtype not in order:
            rtype = "action_item"
        groups[rtype].append(text)
    return {k: groups[k] for k in order if groups.get(k)}


def moments_score_rows(payload: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    moments = payload.get("moments") or []
    rows: list[dict[str, Any]] = []
    for i, m in enumerate(moments):
        if not isinstance(m, dict):
            continue
        quote = (m.get("quote") or "")[:80]
        try:
            score = float(m.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        rows.append(
            {
                "moment": f"#{i + 1} {(quote + '…') if len(m.get('quote') or '') > 80 else quote}",
                "score": score,
                "unit_id": m.get("page_id") or m.get("unit_id"),
                "quote": m.get("quote") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


ACTION_TYPE_LABELS = {
    "action_item": "Action items",
    "decision": "Decisions",
    "open_question": "Open questions",
}
