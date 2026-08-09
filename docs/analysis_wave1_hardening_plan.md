Type: PRODUCT
Authority: Core analysis infrastructure hardening checklist (delivery). Does **not** redefine cache identity, outcomes, or storage atomics — those stay in CONTRACT docs. Companion to [analysis_wave1_plan.md](analysis_wave1_plan.md) §8/§10 residual exit work. Filename retains historical `wave1` as internal delivery id.

# Analysis infrastructure hardening

> **Internal companion** to the core-module delivery history. Product language: shipped **core modules**, not “Wave 1”.

Close contract/exit gaps after core ports landed: parent freshness, UI/cache honesty, moments paragraph profile, eligibility/capability conformance, evidence freshness helper, and focused regression tests.

**Governing contracts:** [analysis-document](contracts/analysis-document.md) · [analysis-result](contracts/analysis-result.md) · [analysis-run-storage](contracts/analysis-run-storage.md) · [notebook-eligibility](contracts/notebook-eligibility.md)

---

## Checklist

| ID | Item | Status |
|----|------|--------|
| H1 | Hard/optional parent freshness vs current planned parent identity → `unavailable_dependency` / omit soft | landed |
| H2 | Themes / Mood / Moments / Summaries / Ask pass live cache identity; stale → warn, no live evidence | landed |
| H3 | `moments` in `PARAGRAPH_PREFERRED` (page_span evidence) | landed |
| H4 | Failed / interrupted never publishes; prior published preserved on module exception | landed |
| H5 | Cache invalidation: page reorder + eligibility fingerprint change | landed |
| H6 | Capability: document `skipped_not_applicable`; wire `emotion` lexicon into identity/envelope | landed |
| H7 | Shared `filter_live_evidence` used by UI/read paths | landed |
| H8 | `page_span` length matches unit text (`char_end - char_start == len(text)`) | landed |
| H9 | Analysis package boundary test (no Streamlit / UI / PageIndex in cores) | landed |
| H10 | This plan + light link from core delivery history | landed |

## Explicit non-goals

- New modules / deferred reinterpretation ports (`ocr_quality` included — **deferred** on [ROADMAP.md](ROADMAP.md); current focus is deepen-in-place robustness/UX)
- Live Ollama / BERTopic / transformer installs
- Shared `transcriptx-analysis` package
- Filling pin-row sha256 for notebook-native `n/a` adaptations
- Broad UI redesign beyond honest read-model / evidence gating (further Analyse UX lives under ROADMAP **Now**, not this checklist)
- Parallel module execution / performance work

## Exit

Hardening pass is done when H1–H9 have code + offline tests green, H10 docs linked, and `# deep-test` pre-release local confidence is not `HIGH RISK`.
