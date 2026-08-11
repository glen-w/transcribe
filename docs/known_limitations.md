Type: GUIDE
Authority: public honesty page for limits and caveats — does not redefine contracts

# Known limitations

Single place for “what can go wrong / what we are not promising.” Product promise: [PRODUCT.md](PRODUCT.md).

## OCR quality

- Handwriting quality varies widely by model, lighting, and page density
- Vision model availability and architectures differ across Ollama builds (a listed “vision” model may still fail to load)
- Preprocess default is **none**; `gentle_contrast` is optional and Pillow-based (no OpenCV in v1)
- **Visual declutter** (import-time, separate from OCR preprocess) defaults **on** (`ingest.visual_declutter_enabled`). v1 ships grey scanner-border crop only; detection is conservative (many pages no-op). Failures fall back to the pre-declutter PNG and never fail import. Changing declutter settings does **not** rewrite existing notebooks — only new imports (or future explicit reprocess).
- **Page ink / blankness metrics** (Review strip + Analyse Overview rollup) are approximate Pillow heuristics over the active render. Ruled lines, shadows, stains, and colour casts can inflate “ink”; hue labels (`black` / `blue` / …) are coarse peaks, not calibrated colour science. Metrics invalidate when active render bytes change; they are not Analyse text modules and do not affect OCR.
- Optional **OCR cleanup** (Run tab / `--cleanup`) adds a **second text-model Ollama call per page** after vision OCR. This can materially increase latency, memory use, and Ollama contention. Cleanup runs sequentially on the page worker after OCR (no extra parallelism). Failures and validator rejections keep raw OCR and never fail the page; rejected model output is discarded
- Cleanup sends OCR text (not page images) to the configured Ollama host; remote hosts still exfiltrate that text by design of that configuration

## Import / PDF

- Encrypted PDFs are rejected
- Very large sources/PDFs fail closed on configured byte/page/render budgets
- PDF rendering uses PyMuPDF; unusual PDF constructs may render poorly

## Jobs and identity

- Fingerprint skip requires **verified** model identity (digest from Ollama discovery). Unverified tags are always re-run
- Cancelling stops scheduling after the current page; in-flight pages still finish
- Mid-job settings changes apply to the next job only

## Archive / cache

- Workspace search/timeline depends on a rebuildable SQLite cache. Corrupt or incompatible caches are deleted and rebuilt
- Cheap `ensure_index` short-circuit uses an explicit **mutation generation** token (`data/cache/archive.generation`), bumped after import/OCR/edit/metadata — not directory mtimes (in-place result edits do not reliably change dir mtime). Per-project rebuild signatures still use result file mtimes inside a rebuild
- Auto-suggested / inherited page dates (unapproved) still index in the archive timeline; approval status is not a filter
- Ollama model discovery metadata is cached by base URL + transport timeout; **Refresh** invalidates. Execution clients stay lightweight

## Privacy

- Local-by-default Ollama. Remote hosts exfiltrate page images by design of that configuration
- Transcribe does not ship cloud OCR providers

## Analysis

- Core analysis modules are shipped; quality follows OCR text quality (noisy handwriting hurts NER, topics, and LLM grounding)
- Prefer **OCR cleanup / second-pass LLM verification** and human review edits to improve text before analysis; a dedicated `ocr_quality` analysis module is deferred ([ROADMAP.md](ROADMAP.md))
- Optional extras (`bertopic`, spaCy NER path, fine-grained emotion) degrade to named capabilities (`unavailable_extra`) rather than silent substitutes
- LLM Summaries / Ask notebook need a **text** Ollama model; missing model → `unavailable_model`. Deterministic `highlights` → `summary` → `insights` still work offline
- Batch Analyse runs from the preset form only; result tabs are read-models. Ask notebook remains an ad-hoc action
- Batch runs use a frozen `AnalysisRunPlan` under a project analysis lock; mid-run settings / text-model / module-list changes apply to the **next** run only
- Streamlit UI interruption does not drop an in-process batch (AnalysisCoordinator). Process crash/reopen marks orphaned attempts and run records `interrupted` without clobbering published results; re-run uses cache hits — no auto-resume
- Freshness is computed via `module_freshness` / planned cache identity — not hand-built identities in the UI
- Analyse tabs share derived `AnalysisHealth` (same `content_revision` + aggregate rules); Ask notebook remains ad-hoc and does not update batch health
- Batch launches freeze an `AnalysisRunPlan` with `plan_hash` at confirm; start refuses hash mismatch and does not re-snapshot settings
- Named presets carry `content_version` (bumped on Settings save); runs record preset identity
- Exports stamp notebook `content_revision` on JSON, manifest, Markdown, and plain text
- Dedicated People & places / Patterns tabs are not shipped; payloads feed Overview / Themes instead (optional polish under the robustness/UX focus, not deferred reinterpretation modules)
- Deferred reinterpretation modules are not scheduled; product focus is deepening the shipped Analyse surfaces
- Analysis results live under project-local `analysis/` and invalidate with text/config/parent changes — see contracts under [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

## Integration

- No TranscriptX dependency. Future notebook handoff is documented separately and is not shipped behaviour: [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)
