Type: PRODUCT
Authority: product review — does not own analysis contracts or module algorithms

# Review: Mood → Moments analysis module

**Date:** 2026-08-19  
**Scope:** `moments` module, View → Mood → Moments UI, and relationship to Highlights / future Slice concepts  
**Status:** Shipped behaviour reviewed; no code changes in this review

## Summary

The **Moments** panel is meant to give users a short, ranked list of **salient quotes** from the notebook with **Jump to page** navigation. In practice, absolute scores cluster around **0.6**, the bar chart looks flat, and the numeric score reads like a calibrated “importance meter” when it is really a **relative ranking helper** with a low ceiling when mood signals are absent.

The module delivers a cheap deterministic browse aid; it does **not** reliably surface “moments” in a human, autobiographical sense.

## Intended user value

| Layer | Stated intent |
|-------|----------------|
| Module catalogue | “Moments worth revisiting” |
| View UI caption | “Salient quotes from the notebook” |
| Wave 1 delivery plan | “Unusual / emotionally strong / high-information passages” |
| Primary action | Ranked quotes + **Jump to page** → Reading |

**What it is not:** [ROADMAP.md](../ROADMAP.md) explicitly separates Mood → **Moments** (analysis salience over quoted pages) from post-1.0 **Slice** (user-confirmed life episodes). [TERMS.md](../TERMS.md) repeats that distinction.

**Related surface:** **Summaries → Highlights** uses a different heuristic (unique words + length + position) and feeds the summary pipeline. Moments is the Mood-facing “revisit these pages” surface.

## Implementation (fork, not parity)

TranscriptX `moments` used speech dynamics (`momentum`, pauses). Transcribe records a **fork** — notebook salience without those signals ([analysis_port_pins.md](../dev/analysis_port_pins.md), [analysis-result.md](../contracts/analysis-result.md)).

- **Module:** `src/transcribe/analysis/modules/moments.py`
- **Algorithm id:** `notebook_salience_fork_v1`
- **Payload:** `moments_payload_v1` — top-N ranked units with scores, per-feature breakdown, quotes, evidence
- **Soft parents (optional):** `emotion`, `sentiment`, `topic_shift` — consumed when published and fresh; not hard dependencies
- **Config:** `analysis.moments.top_n` (default 10)

Batch order runs mood parents before moments (`emotion` 54, `sentiment` 31, `topic_shift` 52, `moments` 58), so a full Analyse preset should enrich scores when those modules succeed.

## Scoring formula

Each analysis unit (typically a **page**) receives a composite score in `[0, 1]`:

| Component | Weight | Source |
|-----------|--------|--------|
| Length | 35% | Token count after stopword removal, capped at 40 tokens → 1.0 |
| Information | 25% | Mean pseudo-IDF **within the notebook** (rarer tokens on that unit score higher) |
| Emotion | 20% | `emotion` unit `intensity` (0 if parent missing) |
| Sentiment | 15% | `abs(sentiment compound)` (0 if parent missing) |
| Topic shift | 5% | 1.0 if unit is a `topic_shift` boundary, else 0 |

Top-N units by score are published; the UI shows a bar chart, a quote list with scores, and jump buttons ([analysis_product_views.py](../../src/transcribe/ui/analysis_product_views.py)).

## Findings

### 1. Scores cluster at 0.6

Observed behaviour: many notebooks show Moments scores at or near **0.6** with little spread on the bar chart.

**Cause A — hard ceiling without mood signals:** When emotion, sentiment, and topic shift contribute nothing, the maximum score is:

```text
0.35 × 1.0 + 0.25 × 1.0 = 0.60
```

Pages that are long enough (≥40 content tokens) and lexically “rich enough” (high within-notebook IDF) **cannot score above 0.60** unless soft features add weight.

**Cause B — homogeneous units:** Diary-style notebooks often have pages of similar length and vocabulary. Length and information components correlate across units, so ranks differ only slightly.

**Cause C — weak mood differentiation:** Emotion uses lexicon hit density; neutral journal prose often yields low intensities. Sentiment uses magnitude only (`|compound|`), so neutral text still contributes little.

**Cause D — display rounding:** The product list formats scores as `{score:.3g}`, so values such as 0.598 and 0.605 both render as **0.6**, hiding small rank differences.

**Cause E — reduced soft features:** If moments runs without fresh `emotion` / `sentiment` / `topic_shift` results, the envelope is `partial: true` with warning `reduced_soft_features`. Ranking then relies almost entirely on length + within-notebook IDF — a weak salience signal for personal notebooks.

Check **Advanced** on the Moments panel for `soft_features_present` and per-row `features` in the payload.

### 2. Absolute scores imply false precision

The UI presents a 0–1 score beside each quote and in a bar chart. Users reasonably interpret this as “strength of moment.” The implementation only guarantees **relative ordering** within one notebook run. Scores are not comparable across notebooks or runs and are not calibrated to human “moment” salience.

### 3. Product promise vs. delivered signal

Wave 1 described “unusual / emotionally strong / high-information passages.” Lexical length + within-doc IDF detects **longer, slightly more vocabulary-diverse pages**, not necessarily emotional peaks or narrative turning points. With soft parents, mood helps only when lexicons/models produce spread — which is often limited on handwritten journal text.

### 4. Naming friction

“Moments” suggests autobiographical episodes. Roadmap and terms already warn this is **not** Slice. The UI caption (“Salient quotes”) is more accurate than the nav label but easy to miss.

## What users should use it for today

1. **Relative ranking** — treat the list as “top N pages by this heuristic,” not as absolute importance.
2. **Quote skim + jump** — read the truncated quote; use **Jump to page** when something looks worth revisiting.
3. **Best with full mood stack** — Thorough (or Custom including `emotion`, `sentiment`, `topic_shift`) gives moments the best chance to spread scores above 0.6.

## Recommendations (not scheduled)

Prioritized options for a future usability or analysis hardening pass:

| Priority | Option | Rationale |
|----------|--------|-----------|
| High | **Rank-first UI** — show #1…#N prominently; de-emphasize or hide raw 0–1 scores | Matches actual semantics; fixes “everything is 0.6” confusion |
| High | **Feature breakdown in product UI** — chips or sub-bars for length / information / emotion / sentiment / shift | Makes the heuristic legible without opening Advanced JSON |
| Medium | **Rescale or normalize scores** for display (e.g. min–max within the published top-N or full unit set) | Spreads bar chart visually while preserving order |
| Medium | **Stronger copy** — caption or tooltip explaining fork, soft parents, and non-absolute scores | Sets expectations; link to this review or known limitations |
| Medium | **Surface `partial` / `reduced_soft_features` in product UI** (not only Advanced) | Users know when they are seeing lexical-only ranking |
| Low | **Algorithm revisit** — paragraph-level units (`paragraph_v1`), corpus-relative IDF, or tighter coupling to `affect_tension` | More engineering; may overlap Highlights; needs contract bump |

Any algorithm change should bump `algorithm_version`, update [analysis-result.md](../contracts/analysis-result.md) if payload semantics change, and add regression tests in `tests/services/test_analysis_wave1d.py`.

## References

- Module: [moments.py](../../src/transcribe/analysis/modules/moments.py)
- UI: [analysis_product_views.py](../../src/transcribe/ui/analysis_product_views.py) (`render_moments_product`)
- Contract: [analysis-result.md](../contracts/analysis-result.md) — `moments_payload_v1`, fork semantics
- Runtime guide: [runtime/analysis.md](../runtime/analysis.md) — View → Mood → Moments
- Roadmap note: [ROADMAP.md](../ROADMAP.md) — Moments ≠ Slice
- Visual intent: [analysis_visual_compare.md](../dev/analysis_visual_compare.md)
