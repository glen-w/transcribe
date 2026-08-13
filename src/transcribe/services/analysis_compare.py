"""Corpus / period comparison baselines for Analyse product charts.

TranscriptX compared speakers on lexical-diversity bar charts. Notebooks have
no speakers — the spiritual analogue is **this notebook vs peers**: either the
entire corpus average or a user-selected period (year or date range).

Read-only over published ``analysis/<module>/published.json`` envelopes. Does
not re-run modules or write durable state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.dates import ApproximateDate
from transcribe.paths import ProjectPaths
from transcribe.persistence.atomic import read_json
from transcribe.services.archive import discover_project_roots

PeriodKind = Literal["all", "year", "range"]

# Metrics that are meaningful as notebook-vs-average categorical bars.
# Paths are dotted keys under envelope["payload"].
COMPARABLE_SPECS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "lexical_diversity": (
        ("ttr", "TTR", "document.ttr"),
        ("mtld", "MTLD", "document.mtld"),
        ("hapax_rate", "Hapax rate", "document.hapax_rate"),
    ),
    "understandability": (
        ("flesch_reading_ease", "Flesch ease", "document.flesch_reading_ease"),
        ("avg_sentence_length", "Avg sentence length", "document.avg_sentence_length"),
        ("gunning_fog_index", "Gunning fog", "document.gunning_fog_index"),
        ("lexical_density", "Lexical density", "document.lexical_density"),
    ),
    "stats": (
        ("unit_count", "Pages / units", "unit_count"),
        ("total_token_count", "Tokens", "total_token_count"),
        ("total_char_count", "Characters", "total_char_count"),
    ),
    "sentiment": (("compound_mean", "Sentiment mean", "global_stats.compound_mean"),),
    "emotion": (("intensity_mean", "Emotion intensity", "global_stats.intensity_mean"),),
    "affect_tension": (("tension_mean", "Affect tension", "global_stats.tension_mean"),),
    "epistemic_markers": (
        ("hedge_share", "Hedge share", "global_stats.hedge_share"),
        ("booster_share", "Booster share", "global_stats.booster_share"),
    ),
}


def payload_get(payload: dict[str, Any], dotted: str) -> Any:
    """Fetch a dotted path from a payload dict; missing → None."""
    cur: Any = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def extract_module_metrics(module_id: str, payload: dict[str, Any] | None) -> dict[str, float]:
    """Pull comparable numeric metrics from one module payload."""
    if not isinstance(payload, dict):
        return {}
    specs = COMPARABLE_SPECS.get(module_id) or ()
    out: dict[str, float] = {}
    for key, _label, path in specs:
        raw = payload_get(payload, path)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        out[key] = value
    return out


def extract_foundations_display(payload: dict[str, Any], module_id: str) -> list[tuple[str, str]]:
    """Human-facing (label, formatted value) pairs for Overview chips."""
    metrics = extract_module_metrics(module_id, payload)
    labels = {key: label for key, label, _ in COMPARABLE_SPECS.get(module_id, ())}
    bits: list[tuple[str, str]] = []
    for key, value in metrics.items():
        label = labels.get(key, key.replace("_", " "))
        if key in {
            "ttr",
            "hapax_rate",
            "lexical_density",
            "hedge_share",
            "booster_share",
        }:
            bits.append((label, f"{value:.3f}"))
        elif key in {
            "mtld",
            "flesch_reading_ease",
            "gunning_fog_index",
            "avg_sentence_length",
        }:
            bits.append((label, f"{value:.1f}"))
        elif key in {"compound_mean", "intensity_mean", "tension_mean"}:
            bits.append((label, f"{value:.3f}"))
        else:
            bits.append((label, f"{value:,.0f}"))
    # Stats / lexical extras that are not in COMPARABLE_SPECS but useful on Overview
    if module_id == "lexical_diversity":
        doc = payload.get("document") if isinstance(payload.get("document"), dict) else {}
        tok = doc.get("token_count")
        if tok is not None:
            bits.insert(0, ("Tokens", f"{int(tok):,}"))
    if module_id == "understandability":
        doc = payload.get("document") if isinstance(payload.get("document"), dict) else {}
        for k, lab in (("word_count", "Words"), ("sentence_count", "Sentences")):
            if doc.get(k) is not None:
                bits.append((lab, f"{int(doc[k]):,}"))
    return bits


@dataclass(frozen=True)
class ComparePeriod:
    kind: PeriodKind = "all"
    year: int | None = None
    range_start: ApproximateDate | None = None
    range_end: ApproximateDate | None = None
    include_undated: bool = True


@dataclass
class MetricBaseline:
    key: str
    label: str
    average: float
    n_notebooks: int
    values: list[float] = field(default_factory=list)


@dataclass
class ModuleBaseline:
    module_id: str
    period: ComparePeriod
    notebooks_scanned: int
    notebooks_with_metric: int
    metrics: dict[str, MetricBaseline] = field(default_factory=dict)
    baseline_label: str = "Corpus average"


def _project_date_bounds(
    root: Path,
) -> tuple[ApproximateDate | None, ApproximateDate | None]:
    try:
        data = read_json(root / "project.json")
    except (OSError, ValueError, TypeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    try:
        start = ApproximateDate.from_dict(data.get("date_start"))
        end = ApproximateDate.from_dict(data.get("date_end"))
    except (ValueError, TypeError):
        return None, None
    return start, end


def notebook_overlaps_period(
    date_start: ApproximateDate | None,
    date_end: ApproximateDate | None,
    period: ComparePeriod,
) -> bool:
    """True when a notebook's diary range intersects the compare period."""
    if period.kind == "all":
        return True
    if date_start is None and date_end is None:
        return period.include_undated
    # Treat missing bound as the other bound (single-point range).
    start = date_start or date_end
    end = date_end or date_start
    assert start is not None and end is not None
    nb_lo = start.to_date_start()
    nb_hi = end.to_date_end()
    if period.kind == "year":
        if period.year is None:
            return False
        lo = date(period.year, 1, 1)
        hi = date(period.year, 12, 31)
    else:
        if period.range_start is None or period.range_end is None:
            return False
        lo = period.range_start.to_date_start()
        hi = period.range_end.to_date_end()
        if hi < lo:
            lo, hi = hi, lo
    return nb_lo <= hi and nb_hi >= lo


def _baseline_label(period: ComparePeriod, n: int) -> str:
    if period.kind == "year" and period.year is not None:
        return f"{period.year} average ({n})"
    if period.kind == "range" and period.range_start and period.range_end:
        a = period.range_start.format_display()
        b = period.range_end.format_display()
        return f"{a}–{b} average ({n})"
    return f"Corpus average ({n})"


def load_module_baseline(
    projects_dir: Path,
    module_id: str,
    *,
    period: ComparePeriod | None = None,
    exclude_project_id: str | None = None,
) -> ModuleBaseline:
    """Average published metrics for ``module_id`` across notebooks in period."""
    period = period or ComparePeriod()
    specs = COMPARABLE_SPECS.get(module_id) or ()
    buckets: dict[str, list[float]] = {key: [] for key, _lab, _path in specs}
    scanned = 0
    for root in discover_project_roots(Path(projects_dir)):
        scanned += 1
        start, end = _project_date_bounds(root)
        if not notebook_overlaps_period(start, end, period):
            continue
        try:
            data = read_json(root / "project.json")
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if exclude_project_id and data.get("id") == exclude_project_id:
            continue
        storage = AnalysisStorage(ProjectPaths(root=root))
        env = storage.read_published(module_id)
        if not env or not env.get("published"):
            continue
        if env.get("outcome") in {
            "failed",
            "insufficient_data",
            "skipped_not_applicable",
        }:
            continue
        payload = env.get("payload")
        metrics = extract_module_metrics(module_id, payload if isinstance(payload, dict) else None)
        for key, value in metrics.items():
            if key in buckets:
                buckets[key].append(value)

    metrics_out: dict[str, MetricBaseline] = {}
    with_any = 0
    for key, label, _path in specs:
        values = buckets.get(key) or []
        if not values:
            continue
        with_any = max(with_any, len(values))
        metrics_out[key] = MetricBaseline(
            key=key,
            label=label,
            average=sum(values) / len(values),
            n_notebooks=len(values),
            values=list(values),
        )
    n_for_label = max((m.n_notebooks for m in metrics_out.values()), default=0)
    return ModuleBaseline(
        module_id=module_id,
        period=period,
        notebooks_scanned=scanned,
        notebooks_with_metric=with_any,
        metrics=metrics_out,
        baseline_label=_baseline_label(period, n_for_label),
    )


def compare_rows(
    current: dict[str, float],
    baseline: ModuleBaseline,
) -> list[dict[str, Any]]:
    """Rows ready for a categorical this-vs-average bar chart."""
    rows: list[dict[str, Any]] = []
    for key, label, _path in COMPARABLE_SPECS.get(baseline.module_id, ()):
        if key not in current or key not in baseline.metrics:
            continue
        base = baseline.metrics[key]
        rows.append(
            {
                "key": key,
                "label": label,
                "this": current[key],
                "average": base.average,
                "n": base.n_notebooks,
                "delta": current[key] - base.average,
            }
        )
    return rows
