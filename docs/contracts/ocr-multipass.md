Type: CONTRACT
Authority: self — MultiPass OCR orchestration, job records, rank/composite phases

# OCR multipass

Related: [page-result.md](page-result.md), [ocr-preference.md](ocr-preference.md).

## Purpose

Run multiple vision OCR models over the same notebook (or page set), retain competing succeeded attempts, then optionally rank raws and produce a **composite** candidate (user-facing **merged draft**) with a text model. Composite is a derived LLM reconciliation of independent vision attempts. It is never ranked among raws and never counted as an OCR vote.

## Job record

- Path: `jobs/multipass_<pass_id>.json`
- `format`: `transcribe.ocr-multipass-job`
- `schema_version`: `1`
- Frozen `MultiPassPlan`: ordered vision models (name + digest + verified), shared prompt/preprocess/generation options, optional per-attempt cleanup plan, ranker/composite text model identity, page targets, `force`, `auto_activate_composite`, prefer-mode snapshot, `pass_id`, `cleanup_enabled` (vision-phase cleanup; default **false**), optional `compare_only` (rank/composite over existing attempts; no vision phases)

## Phases

1. **Vision phases** — for each model, run a single-model OCR plan with `activate=false` and stamp `pass_id` / `attempt_kind=vision` on attempts. Skip when fingerprint matches any succeeded vision attempt (verified identity required). Cleanup is **off** unless the frozen plan sets `cleanup_enabled`. After **3 consecutive generate timeouts** on a vision plan, remaining pages for that model are skipped; the next model still runs. User cancel stops remaining pages of the current model and **does not start remaining models**.
2. **Per-page barrier** — once a page has ≥2 succeeded vision attempts for this `pass_id` (or all vision phases finished for that page), run rank then composite for that page. Cancel still ranks/composites pages that already have ≥2 successes. Rank/composite candidates are the latest succeeded-with-text vision attempt **per model identity** (same as Review), including attempts from earlier jobs when this pass has fewer than two.
3. **Rank** — text-only v1; persist `comparison` with vision-only `ranked_attempt_ids` (best-first). Malformed rank → leave `comparison` null.
4. **Composite** — merge candidates into one `attempt_kind=composite` attempt with `source_attempt_ids`, merge-model provenance (name, digest when known, prompt id/version/sha256, timestamps). Soft-fail → no composite attempt. A composite is **current** only while `source_attempt_ids` equals the succeeded vision attempts that would be inputs to a new merge (latest succeeded vision per model identity). A new/replaced succeeded source attempt makes prior composites **stale**; they are retained. Rank/composite re-run when the page is missing a **current** (non-stale) composite for this pass.
5. **Activation** — if `auto_activate_composite` and composite succeeded → set active (and preferred when prefer mode is `prefer_is_promote`) and ledger `auto_composite`, seeding Transcription from the merged draft. Else if page had no prior succeeded active → activate best-ranked raw (or newest vision success). Do not seed the editor from a stale composite. User-facing labels and when to disable: [runtime/ocr.md](../runtime/ocr.md#seed-transcription-from-merged-draft-after-multipass).
6. **Compare-only** — UI **Rank and merge existing OCR** (Review and Transcribe) runs rank + composite on on-disk vision successes **without** vision phases. Job record may set `compare_only: true` and list the model names already present as merge inputs. Requires ≥2 distinct model identities with non-empty succeeded text, plus a text/cleanup ranker model. A new `pass_id` is minted; prior composites become stale when source ids change.

## Crash / resume

- Job record persists phase cursor (model index + page progress) and `cleanup_enabled`. Resume continues from incomplete vision phases; rank/composite re-run only for pages missing a current `comparison` for this `pass_id` or missing a **current** (non-stale) composite when expected.
- UI starts compare in a background thread (`MultiPassCoordinator.start`); CLI `multipass` remains `run_blocking`. Stop after current page cancels the inner vision job and remaining models.
- Page mutation lock and job lock follow existing project job conventions.

## Non-goals

- Image-conditioned ranking (deferred)
- Auto multipass on import
- Silencing single-model Start into multipass
