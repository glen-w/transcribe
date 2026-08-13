Type: GUIDE
Authority: public honesty page for limits and caveats — does not redefine contracts

# Known limitations

Single place for “what can go wrong / what we are not promising.” Product promise: [PRODUCT.md](PRODUCT.md).

## OCR quality

- Handwriting quality varies widely by model, lighting, and page density
- Vision model availability and architectures differ across Ollama builds (a listed “vision” model may still fail to load)
- Preprocess default is **none**; `gentle_contrast` is optional and Pillow-based (no OpenCV in v1)
- **Visual declutter** (import-time, separate from OCR preprocess) defaults **on** (`ingest.visual_declutter_enabled`). Ships grey/light-grey scanner-bed crop, stark-white overscan/gutter crop, and residual rounded-corner bed wedges; detection is conservative (many pages no-op). Failures fall back to the pre-declutter PNG and never fail import. Changing declutter settings alone does **not** rewrite existing notebooks — use **Settings → Configuration → Re-apply visual declutter** (or a new import) to crop existing pages. Re-apply does not re-run OCR and cannot restore already-cropped margins when turned off.
- **Page ink / blankness metrics** (Review strip + Analyse Overview rollup) are approximate Pillow heuristics over the active render. Ruled lines, shadows, stains, and colour casts can inflate “ink”; hue labels (`black` / `blue` / …) are coarse peaks, not calibrated colour science. Metrics invalidate when active render bytes change; they are not Analyse text modules and do not affect OCR.
- Optional **OCR cleanup** (Run tab / `--cleanup`) adds a **second text-model Ollama call per page** after vision OCR. This can materially increase latency, memory use, and Ollama contention. Cleanup runs sequentially on the page worker after OCR (no extra parallelism). Failures and validator rejections keep raw OCR and never fail the page; rejected model output is discarded
- Cleanup sends OCR text (not page images) to the configured Ollama host; remote hosts still exfiltrate that text by design of that configuration
- Vision OCR always sends a `num_predict` cap (default **4096**). That stops a looping generate from running until the HTTP timeout. Hitting the cap records `truncated` in allowlisted provider metadata and does **not** fail the page. Default `num_predict` is omitted from skip fingerprints so existing attempts still match
- Ollama **generate timeouts are not retried**. Connection errors and 5xx responses still retry (3 attempts). A hang therefore fails in one HTTP timeout (default 300s), not ~15 minutes
- **General vision-language models** (for example `llava`) can hang or time out on dense notebook scans even when listed as vision-capable. Prefer OCR-oriented tags for handwriting. After **3 consecutive timeouts** on one frozen vision plan, remaining pages for **that model** are skipped (progress `circuit_open`); a multipass compare continues with the next model
- Some Ollama “vision” tags still **fail to load** on a given build (example: `llama3.2-vision:11b` → `unknown model architecture: 'mllama'` on Ollama 0.32.x — see [ollama#16547](https://github.com/ollama/ollama/issues/16547)). Transcribe classifies these as non-retriable `model_load` errors and **skips remaining pages for that model after the first failure** (same `circuit_open` path as timeouts). Prefer a working alternate family (for example `granite3.2-vision` or `minicpm-v`) until the host Ollama/model pair loads cleanly. Batch OCR inherits the same per-notebook circuit (one bad model does not keep calling every page in that notebook).
- **Multipass compare** runs each selected vision model across the notebook, then a text-model **rank** (text-only v1) and optional **composite** merge. Cost scales with model count × pages plus rank/composite calls; on **Batch** multipass it also scales with notebook count. Composite is assistive, not ground truth. Rank failure falls back to chronological attempt order in Review. Vision phases **default cleanup off** (CLI `--cleanup` / UI “Clean OCR during compare” to opt in). The UI starts compare in a background thread like single-model Start; Stop cancels remaining pages of the current model and remaining models (and does not start remaining batch notebooks). Rank/composite still run for pages that already have ≥2 succeeded vision attempts

## Import / PDF

- Encrypted PDFs are rejected
- Very large sources/PDFs fail closed on configured byte/page/render budgets
- PDF rendering uses PyMuPDF; unusual PDF constructs may render poorly
- After corpus index recovery, retained quarantine artifacts under `data/corpus/quarantine/` are doctor **warnings** (`corpus_quarantine_present`) until an operator deletes them — they do not block a healthy corpus

## Jobs and identity

- Fingerprint skip requires **verified** model identity (digest from Ollama discovery). Unverified tags are always re-run
- Cancelling stops scheduling after the current page; in-flight pages still finish. During compare, remaining vision models are not started; rank/composite still run for pages that already have ≥2 succeeded vision attempts
- Mid-job settings changes apply to the next job only

## Archive / cache

- Workspace search/timeline depends on a rebuildable SQLite cache. Corrupt or incompatible caches are deleted and rebuilt
- Cheap `ensure_index` short-circuit uses an explicit **mutation generation** token (`data/cache/archive.generation`), bumped after import/OCR/edit/metadata — not directory mtimes (in-place result edits do not reliably change dir mtime). Per-project rebuild signatures still use result file mtimes inside a rebuild
- Auto-suggested / inherited page dates (unapproved) still index in the archive timeline; approval status is not a filter. Review states this in-product and offers batch approve/ignore for suggestions.
- Diary date auto-extract (early page text) understands compact `YYMMDD`, `DD/MM/YYYY`, `DD/MM/YY`, `YYYY-MM-DD`, and English month names (`Jan 2, 2018`). Ambiguous numerics are **day/month** (DMY). Time-of-day is ignored. OCR can still garble stamps; pages that look stamped but fail to parse stay **undated** (no inheritance) until Review
- Ollama model discovery metadata is cached by base URL + transport timeout; **Refresh** invalidates. Execution clients stay lightweight. Model information shows verified vs unverified identity (digest) and preference last-used when available.
- Archive notebook strip paging defaults to **show all** (`ui.archive_notebooks_initial = 0`). A positive value loads that many cards before **Show more**; session state can expand further until rerun/reset.

## Privacy

- Local-by-default Ollama. Remote hosts exfiltrate page images by design of that configuration
- Transcribe does not ship cloud OCR providers

## Analysis

- Core analysis modules are shipped; quality follows OCR text quality (noisy handwriting hurts NER, topics, and LLM grounding)
- Prefer **OCR cleanup / second-pass LLM verification** and human review edits to improve text before analysis; a dedicated `ocr_quality` analysis module is deferred ([ROADMAP.md](ROADMAP.md))
- Optional extras (`bertopic`, spaCy NER path, fine-grained emotion) degrade to named capabilities (`unavailable_extra`) rather than silent substitutes
- LLM Summaries / Ask notebook need a **text** Ollama model; missing model → `unavailable_model`. Deterministic `highlights` → `summary` → `insights` still work offline
- Batch Analyse runs from the preset form only; result tabs are read-models. Ask notebook remains an ad-hoc action
- **Analyse → Batch** runs the same frozen plan template sequentially across notebooks (dual progress bars: notebooks + modules). Empty-text notebooks are skipped; there is no OCR-style Force flag. This is orchestration only — not cross-notebook / corpus-level Analyse
- Batch runs use a frozen `AnalysisRunPlan` under a project analysis lock; mid-run settings / text-model / module-list changes apply to the **next** run only
- Streamlit UI interruption does not drop an in-process batch (AnalysisCoordinator). Process crash/reopen marks orphaned attempts and run records `interrupted` without clobbering published results; re-run uses cache hits — no auto-resume
- Freshness is computed via `module_freshness` / planned cache identity — not hand-built identities in the UI
- Analyse tabs share derived `AnalysisHealth` (same `content_revision` + aggregate rules); Ask notebook remains ad-hoc and does not update batch health
- Batch launches freeze an `AnalysisRunPlan` with `plan_hash` at confirm; start refuses hash mismatch and does not re-snapshot settings
- Named presets carry `content_version` (bumped on Settings save); runs record preset identity
- Exports stamp notebook `content_revision` on JSON, manifest, Markdown, and plain text
- Dedicated Patterns tab is not shipped; payloads feed Themes instead (optional polish under the **usability wave**, not deferred reinterpretation modules — [usability_wave_plan.md](usability_wave_plan.md))
- **People & places** tab maps NER place labels (GPE/LOC/FAC) for the open notebook; **Notebooks → Places** aggregates across notebooks. Geocoding via OpenStreetMap Nominatim is opt-in and cached under `data/cache/geocode.json`
- Overview / Mood **corpus or period compare** averages other notebooks’ published numeric metrics (this notebook excluded). Year / date-range use diary `date_start`/`date_end`; undated notebooks count only under “Entire corpus”. Peers without a published result for that module are skipped — charts need at least one peer with data
- **Word themes** offer **Basic** (static frequency cloud) or **Advanced** (interactive explorer with search / top N / min value / sort / CSV — TranscriptX explorer controls). Advanced uses a vendored `wordcloud2.js` (offline). Basic needs the optional ``wordcloud`` package from ``.[ui]``. Analysis still stores frequencies only — images/explorer state are not durable artifacts.
- Deferred reinterpretation modules are not scheduled; product focus is the usability wave (trust, Analyse product UX, first-run, daily workbench) for the shipped surfaces — [ROADMAP.md](ROADMAP.md) **Now**
- Analysis results live under project-local `analysis/` and invalidate with text/config/parent changes — see contracts under [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

## Integration

- No TranscriptX dependency. Future notebook handoff is documented separately and is not shipped behaviour: [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)
