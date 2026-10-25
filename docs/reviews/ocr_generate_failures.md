# Review: OCR generate failures (token-repeat and related)

**Date:** 2026-10-23  
**Scope:** Ollama vision generate, skip/resume, glm-ocr recipe, SIGINT leftover generates — reconstructed from last night’s Nightshift `transcribe-night` run plus page-result JSON on notebook `black`  
**Status:** Review landed. Hardening in this change set: classify `token_repeat` (no identical retry), glm-ocr `repeat_penalty` recipe, truncated+repetition fails, SIGINT `/api/abort`, `:latest` identity alias for skip. Nightshift caps are unchanged.

This review does not redefine on-disk schemas. Attempt `error.code` values stay free-form strings; `token_repeat` is a new code alongside `timeout`, `http_error`, `empty_output`, `model_load`.

## A. Evidence (night of 2026-10-22/23)

Notebook `black`, 184 pages. Job `com.glen.nightshift.transcribe-night` pid 41123, `bulk-run notebooks` with `qwen2.5vl:7b`, `glm-ocr`, `granite3.2-vision`. Window 01:00–07:00; cut at `TIER_MAX_MINUTES=90` (03:56 local, Transcribe exit 130).

| Pass | Outcome |
|------|---------|
| `qwen2.5vl:7b` | 183 skipped (already succeeded); 1 token-repeat (`black_146`) |
| `glm-ocr` | 69 finished: **29 succeeded, 39 token-repeat, 1 timeout** (`black_049`, 301s); 1 SIGINT in-flight (`black_069`); 114 unstarted |
| `granite3.2-vision` | never started |

glm fail rate among finished pages: **58%**. Token-repeat pages were mixed with successes from the first minutes of glm (02:27 local). transcriptx-night overlapped from ~03:01 — after repeats had already started. Contention may explain the one timeout; it does not explain the 39 aborts.

The documented loop guard (`num_predict=4096` → `truncated`, still **succeeded**) **did not fire on glm**. llama.cpp aborted first. Log line:

```text
{"error":"prediction aborted, token repeat limit reached"}
```

Stored on the page as:

```json
"error": {
  "code": "http_error",
  "message": "{\"error\":\"prediction aborted, token repeat limit reached\"}",
  "retriable": true
}
```

Example: `black/results/3da3946e40d9419c88fb1ad4f3a397ed.json`, glm attempt `7fff9cbc…` (01:46:51Z–01:48:42Z, ~111s) after an earlier glm abort the previous evening in **13s** (`7442b87a…`). The long wall-clock is consistent with `call_with_retries` repeating the **same** 5xx generate three times.

The same page has a **granite** attempt that *did* hit the cap: `eval_count=4096`, `truncated=true`, `status=succeeded`, body looping “I'm talking lily…”. Skip-on-success would keep that garbage forever.

## B. Current behaviour (before this change set)

| Surface | What it did |
|---------|-------------|
| Generate options | Global `{temperature: 0.0, num_predict: 4096}` only. No `repeat_penalty`, `repeat_last_n`, `stop`. |
| glm-ocr host Modelfile | `PARAMETER temperature 0` only. Template `{{ .Prompt }}`. Tag listed as **`glm-ocr:latest`**. Nightshift / CLI pass **`glm-ocr`**. |
| 5xx mapping | Fatal-load markers → `model_load` (not retried). Everything else ≥500 → `http_error`, **retriable**. Token-repeat is not a marker. |
| HTTP 200 | Only `payload["response"]` is read. A JSON `error` field on 200 is ignored. |
| Client retries | 3 attempts, 0.5s / 1s backoff, identical body. Timeouts are not retried. |
| Job skip | Succeeded + fingerprint match + **verified identity**. Failed/interrupted never skip. |
| Truncated text | Success. `truncated` is metadata only. |
| SIGINT | No handler. In-flight attempt stays `running` until next `load(reconcile=True)` → `interrupted`. No `POST /api/abort`. |
| Recipes | DeepSeek-OCR only (`free_ocr` prompt). glm-ocr has none. |

Identity skip is dead for glm (and granite) on this host: `resolve_model_identity` requires an **exact** `/api/tags` name. `glm-ocr` ≠ `glm-ocr:latest` → `model_identity_verified=false` → `_should_skip` always false. That matches last night’s glm `skipped=0` on 184 pages. `qwen2.5vl:7b` matches the tag exactly, so 183 pages skipped.

## C. Gaps

1. **Token-repeat is a looping abort, not a transient 5xx.** Retrying the same payload burns ~2 extra generates per failed page (last night’s glm median ~72s includes those retries) and still persists `http_error` / `retriable=true`.
2. **No glm-ocr recipe.** The tag is 1.1B F16 with no `repeat_penalty` in its Modelfile. Generic `faithful_markdown` plus llama.cpp’s default sampler still aborted 39/69 pages.
3. **Truncated looping text is sticky success.** granite on the sampled page is already in that state. Next job skips it.
4. **SIGINT leaves Ollama generating.** Nightshift `kill -INT` the process group; Transcribe does not abort the in-flight `/api/generate`. The next client can stall.
5. **`:latest` alias breaks skip** for `glm-ocr` and `granite3.2-vision` even after a page succeeds. A glm `repeat_penalty` fingerprint change would not skip those successes until identity verifies.

## D. Decisions (locked)

Owners are Transcribe modules, not Nightshift.

| ID | Decision | Owner | Fingerprint impact |
|----|----------|-------|--------------------|
| D1 | Classify `"token repeat limit reached"` as `token_repeat`, **not retriable** with the same payload. Also treat HTTP 200 bodies that carry that `error` string. | `providers/ollama.py` | None |
| D2 | Do **not** add a consecutive-token-repeat circuit. Successes were interleaved; skipping the rest of glm would drop pages that work. | `services/job.py` | None |
| D3 | glm-ocr recipe: overlay `repeat_penalty: 1.2`. **Do not change the prompt** (`faithful_markdown` stays). Do not set `repeat_penalty` globally. | `ocr_model_recipes.py` + plan freeze | glm only: `generation_options` gains `repeat_penalty` → hash changes → succeeded glm pages re-run once with the recipe, then skip if identity is verified. qwen/granite hashes unchanged. |
| D4 | `truncated` **and** repetition (`review_signals` regex) → persist `failed` / `token_repeat`. Do not replace a prior good active reading. Do not repair historical truncated successes in this cut. | `services/job.py` | None (failed pages never skip) |
| D5 | On `KeyboardInterrupt`: persist `interrupted`, `POST /api/abort` `{name: model}`, re-raise. Abort is best-effort. | `job.py` + `ollama.py` | None |
| D6 | `resolve_model_identity` treats `tag` and `tag:latest` as the same name. Required so D3 skip actually engages on this host. | `providers/ollama.py` | New verified plans include `model_identity_verified=true` and a digest, so they will not skip-match old unverified glm attempts (one re-OCR, then skip). |
| D7 | Nightshift `TIER_MAX_MINUTES`, TX yield, and model order stay. Re-measure after one night. Token-repeats started before TX. | — | — |

Optional one retry with different options is **not** in this cut. Fail the page; the next job retries with the recipe (D3) because skip is success-only.

Prompt rewrite for glm-ocr is **v2** only if options-only still aborts >30% on a spot-check.

## E. Follow-ups (not this cut)

- Historical repair of truncated+repetition `succeeded` granite/glm attempts (same pattern as empty-success repair).
- Drop glm-ocr from Nightshift’s compare set if the recipe still aborts >30% on a real night.
- Yield the **current** notebook when transcriptx-night starts (Nightshift), only if timeouts cluster under overlap after D1–D5.
- If Review finds glm-ocr `truncated` tails are padding rather than leftover page text, lower recipe `num_predict` (that key is already fingerprint-significant).

## Spot-check (2026-10-23, after this change set)

Four `black` pages that token-repeated last night, glm-ocr only, recipe options `{temperature: 0, num_predict: 4096, repeat_penalty: 1.2}`, faithful_markdown, **not persisted**:

| page_id prefix | elapsed | eval_count | truncated | repetition regex | outcome |
|----------------|--------:|-----------:|-----------|------------------|---------|
| `9964f6ac` | 41.5s | 4096 | yes | no | succeeded |
| `e00df36a` | 39.5s | 4096 | yes | no | succeeded |
| `d522fb68` | 40.0s | 4096 | yes | no | succeeded |
| `5bd8930c` | 55.6s | 4096 | yes | no | succeeded |

**4/4 no token-repeat abort.** Previews read as diary text, not the granite-style “I'm talking lily…” loop. They still hit `num_predict` (~12–17k chars). That is dense-page truncation, not the abort that burned last night. `num_predict` stays 4096; leave lowering it for a later recipe tune if Review finds the tails are padding.

## F. Tests that pin the gaps

- `tests/providers/test_ollama_http.py` — token-repeat 5xx and 200-`error` are one shot; `:latest` identity alias; `/api/abort` called.
- `tests/unit/test_ocr_empty_recipe_compare.py` — glm recipe options overlay; qwen still has no recipe.
- `tests/unit/test_fingerprint.py` — `repeat_penalty` changes the hash; default `num_predict` still omitted.
- Job tests — truncated+repetition fails; KeyboardInterrupt persists `interrupted` and calls abort.
