# Transcribe product

**Transcribe** is a local-first workbench for turning handwritten notebook pages into editable, portable text.

## Is this for me?

Yes if you keep paper notebooks (or scans of them) and want searchable, editable
text while keeping images and results on disk you control.

No if you need cloud OCR, audio transcription, or speaker diarization — those
are out of scope. Transcribe does not depend on TranscriptX.

## Promise

On your machine you can:

1. Import JPEG/PNG/PDF pages into a notebook folder
2. Transcribe them with a local Ollama vision model
3. Review and correct text page by page
4. Optionally analyse the text (Overview, Themes, Mood, Summaries, Detect, People & Places)
5. Export Markdown, plain text, HTML/EPUB/PDF, and a portable notebook JSON file
6. Back up and restore the full workspace as a local ZIP

Notebook identity, original scans, and human edits survive renames and re-OCR.
Bulk import of many folders is supported. Contracts: [notebook-corpus](contracts/notebook-corpus.md), [source-asset](contracts/source-asset.md), [import-run](contracts/import-run.md), [corpus-integrity](contracts/corpus-integrity.md).

## Surfaces today

| Surface | Role |
|---------|------|
| Streamlit UI (port **8510**) | Primary interactive workflow |
| CLI (`transcribe` / `python -m transcribe`) | Automation and integrity checks |
| Shared Python services | Single implementation for UI and CLI |

Supported entrypoints: [public_surfaces.md](public_surfaces.md).

## Product boundaries (v1)

**In scope**

- Local Ollama vision models only (no cloud OCR providers)
- Page-first domain (ordered pages, not timed speaker segments)
- Human edits preserved separately from raw OCR attempts
- Portable export without required absolute paths
- Full-workspace backup / restore (`transcribe.workspace-backup` ZIP; replace-only onto current mounts)
- Core notebook analysis modules and Analyse (optional local text Ollama for LLM modules)
- Deepen-in-place: usability wave — trust, Analyse product UX, first-run operability (**U2** open except Home/Diagnostics from GUI alignment), daily workbench (**U3** done); OCR fail-fast, Analyse corpus-compare, Moments/chart jump → Reading, and Analyse/View split are shipped deepen-in-place ([ROADMAP.md](ROADMAP.md) · [usability_wave_plan.md](usability_wave_plan.md))

**Path to 1.0:** package **0.8.8** (I0–I5 landed plus post-U3 product cuts and Docker-preferred install docs) → remaining **U2** + **I6** → cut **0.9.0** → **0.9-1** unfamiliar testing ([dev/user_testing_0_9.md](dev/user_testing_0_9.md)) → **1.0** freeze. Detail: [ROADMAP.md](ROADMAP.md) Path to 0.9.0.

**Out of scope for current core**

- Cloud OCR / hosted inference as a first-class provider
- Audio transcription or speaker diarization
- Shipping TranscriptX integration (future seam only — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md))
- OpenCV-based preprocessing pipelines (optional Pillow profiles only; default is none). Visual declutter is a separate Pillow lane (scanner-bed, stark-white overscan, corner-wedge crop on import + explicit re-apply), not OCR preprocess.
- Deferred analysis reinterpretations and `ocr_quality` — **deferred** on [ROADMAP.md](ROADMAP.md); prefer second-pass LLM OCR cleanup/verification for text quality
- Autobiography / contextual imports (WhatsApp, photo libraries, Slices, reconstruction) — **not this product**. The write-up stays on file in [ROADMAP.md](ROADMAP.md) for a future separate product ([scope lean](ROADMAP.md#scope-lean--24-sep-2026))

## Not this product (on file)

**1.0 is** this notebook workbench: transcribe handwritten pages, compare vision models, export a fine-tune set and bring a hand-specific model back, read / tag / explore notebooks. Reach a public cut via **0.9.0** (U2 + infra) then **0.9-1** unfamiliar testing if a stranger should install it ([ROADMAP Path to 0.9.0](ROADMAP.md#path-to-090--09-1--10)).

Transcribe does not grow into an autobiography workbench after that cut. The old 1.1–2.0 sequencing stays in [ROADMAP.md](ROADMAP.md) **on file** for a future separate product. It is not shipped behaviour and it is not this repo’s backlog.

## Honesty

See [known_limitations.md](known_limitations.md) for model quality, PDF quirks, analysis capability caveats, and privacy. Shipped vs planned analysis: [ROADMAP.md](ROADMAP.md) · [analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md).

**Miss list.** Review **Failed OCR** is the list of pages the vision pass did not read (`empty_output` and other failures). A miss stays on that list. It is not a silent success.

**VL OCR ≠ opt-in LLM.** The vision model that reads the page image is the OCR door. Summaries and Ask notebook are a separate text-model switch. They stay unavailable when that text model is missing. Turning on a text model does not re-read the scan.

**Won't.** Cloud OCR, audio transcription, speaker diarization, and an autobiography workbench. Transcribe is not TranscriptX. The gate verb for pages is **import**. The human step after OCR is **correct**.

| Claim | Quote |
| --- | --- |
| Notebook workbench, not autobiography | This file, “Not this product”; [ROADMAP scope lean](ROADMAP.md#scope-lean--24-sep-2026) |
| Human edits survive re-OCR | This file, “Notebook identity, original scans, and human edits survive renames and re-OCR.” |
| Miss list is Failed OCR | [known_limitations.md](known_limitations.md) — Empty OCR is `empty_output`; Review **Failed OCR** is the queue |
| Vision OCR ≠ text LLM | [known_limitations.md](known_limitations.md) — thinking vision models vs “LLM Summaries / Ask notebook need a **text** Ollama model” |
| PR CI has no vision GPU | Job `compose-config` (`scripts/release/assert_compose_bind.sh` on `docker-compose.yml` only) and job `tests` (pytest). Neither pulls a vision model. Design for a later import→OCR smoke: [dev/smoke_kit_import_ocr.md](dev/smoke_kit_import_ocr.md) |

## Related

- Architecture shape: [ARCHITECTURE.md](ARCHITECTURE.md)
- Contracts: [CONTRACT_INDEX.md](CONTRACT_INDEX.md)
- User flows: [user_guide.md](user_guide.md)
- Workspace backup / restore: [backup_and_restore.md](backup_and_restore.md)
