Type: CONTRACT
Authority: self — MultiPass OCR orchestration, job records, rank/composite phases

# OCR multipass

Related: [page-result.md](page-result.md), [ocr-preference.md](ocr-preference.md).

## Purpose

Run multiple vision OCR models over the same notebook (or page set), retain competing succeeded attempts, then optionally rank raws and produce a **composite** candidate with a text model. Composite is never ranked among raws.

## Job record

- Path: `jobs/multipass_<pass_id>.json`
- `format`: `transcribe.ocr-multipass-job`
- `schema_version`: `1`
- Frozen `MultiPassPlan`: ordered vision models (name + digest + verified), shared prompt/preprocess/generation options, optional per-attempt cleanup plan, ranker/composite text model identity, page targets, `force`, `auto_activate_composite`, prefer-mode snapshot, `pass_id`

## Phases

1. **Vision phases** — for each model, run a single-model OCR plan with `activate=false` and stamp `pass_id` / `attempt_kind=vision` on attempts. Skip when fingerprint matches any succeeded vision attempt (verified identity required).
2. **Per-page barrier** — once a page has ≥2 succeeded vision attempts for this `pass_id` (or all vision phases finished for that page), run rank then composite for that page.
3. **Rank** — text-only v1; persist `comparison` with vision-only `ranked_attempt_ids` (best-first). Malformed rank → leave `comparison` null.
4. **Composite** — merge candidates into one `attempt_kind=composite` attempt with `source_attempt_ids`. Soft-fail → no composite attempt.
5. **Activation** — if `auto_activate_composite` and composite succeeded → set active (and preferred when prefer mode is `prefer_is_promote`) and ledger `auto_composite`. Else if page had no prior succeeded active → activate best-ranked raw (or newest vision success).

## Crash / resume

- Job record persists phase cursor (model index + page progress). Resume continues from incomplete vision phases; rank/composite re-run only for pages missing a current `comparison` for this `pass_id` or missing composite when expected.
- Page mutation lock and job lock follow existing project job conventions.

## Non-goals

- Image-conditioned ranking (deferred)
- Auto multipass on import
- Silencing single-model Start into multipass
