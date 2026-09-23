# Project review and stocktake

**Date:** 2026-09-23  
**Package:** 0.8.8 (`pyproject.toml`, `transcribe.__version__`)  
**Git:** `main` at `c3af87a` (2026-09-22), in step with `origin/main`  
**Scope:** Whole repository — product surface, code size, tests, docs, and distance to 0.9.0 / 1.0  
**Method:** Read of product, architecture, roadmap, usability, and infrastructure plans, plus a measured source-line count. The offline test suite was not re-run for this note.

This file is a snapshot. It does not change schemas or support policy. Module-level evidence already written up lives in [docs/reviews/architecture_from_evidence.md](../docs/reviews/architecture_from_evidence.md) (2026-09-03).

## Verdict

Transcribe is a **finished notebook workbench in the middle of its release path**, not an unfinished OCR prototype.

The promised loop is implemented end to end: import scans, local Ollama vision OCR (including multipass compare), review beside the page, analyse with a 25-module set, detect patterns, export, and back up the workspace. Corpus bulk import, batch OCR, and batch Analyse are runtime-normative, with acceptance suites in tree. Authority is directories of JSON and page images. SQLite is a rebuildable search cache.

What remains before a **0.9.0** cut is narrow and already named:

- **U2.2** — a sample notebook a new user can open without their own scans
- **U2.4** — the first-run docs acceptance item is still unchecked in the usability plan, after the 0.8.8 public-docs reframe
- **I6** — nightly heavier offline tests, Docker image smoke inside release checks, and GitHub issue templates

**1.0** is a freeze after unfamiliar-user testing (**0.9-1**), not another feature wave. The autobiography programme (photos, messages, Slices) is documented and correctly gated behind that freeze.

## What it is

Local-first workbench for handwritten notebook pages. Streamlit on port **8510** is the primary surface. The CLI (`transcribe` / `python -m transcribe`) calls the same services. Docker Compose is the preferred install; host Python via `./transcribe.sh` is the advanced path.

| In the product | Held outside v1 |
|----------------|-----------------|
| JPEG/PNG/PDF import, visual declutter, page-first notebooks | Cloud OCR providers |
| Ollama vision OCR, cleanup, multipass rank/composite | Audio transcription, speaker diarization |
| Human edits kept apart from raw OCR attempts | A TranscriptX library dependency |
| Analyse, Detect, People & Places, export, workspace ZIP backup | OpenCV preprocess; schema migrators |
| | Context corpus (`data/context/`) before 1.0 |

Trust model matches a single-user machine: loopback bind by default, no authentication, remote Ollama and Nominatim geocoding are explicit exits for images or place names. Backup ZIPs are plaintext.

## History in the repo

| Fact | Value |
|------|--------|
| First commit | 2026-08-07 — “Initial release of local-first notebook OCR with Ollama.” |
| Commits on `HEAD` | 108 (entire history is since that date) |
| Latest commit | 2026-09-22 — logo padding |
| Tags present | `v0.3.0` … `v0.6.5`, then `v0.8.5`–`v0.8.8` (no `v0.7` / `v0.8.0` tags in the local tag list) |
| Authors in shortlog | Glen, Glen Wright, Cursor Agent |

The version ladder in [docs/ROADMAP.md](../docs/ROADMAP.md) is the authority for what each number means. Package **0.8.8** is the I5 / Docker-preferred-docs cut. The working tree at review time was clean.

## Size

Source lines below are **substantive code** (blanks and comments stripped). Markdown, JSON, YAML, and TOML are excluded from the headline. Counters: tokei 14.0.0, scc 4.0.0, cloc 2.08; radon 6.0.1 is a Python cross-check. File list: 491 git-tracked paths after dropping vendored, cache, archive, and artifact trees. Estimate is the median of the three code columns.

### Role summary

| Role | Estimate | Range | Files |
|------|----------|-------|-------|
| Product (`src/`) | **51,885** | 51,530–54,029 | 235 |
| Tests | **22,164** | 22,149–22,374 | 138 |
| Scripts | **789** | 774–807 | 9 |
| **Maintained** (product + tests + scripts) | **74,838** | 74,453–77,210 | — |

Python-only product SLOC: trio median **50,983** (range 50,629–53,128). Radon reports 51,612 and agrees within 1%, so it does not pull the headline.

Tests are about **43%** of product size. That is a large, intentional suite, concentrated on services, persistence, and acceptance gates. The UI is the largest package and is omitted from the coverage gate (see Quality).

### Product layers

Estimates are Python unless noted.

| Layer | Estimate | Share of product | Role |
|-------|----------|------------------|------|
| `ui` | 17,546 Python + 901 JavaScript | ~36% | Streamlit shell, Review workbench, Library, Analyse/View, settings |
| `services` | 11,324 | ~22% | Project, jobs, OCR compare, export, archive, backup, places |
| `analysis` | 7,184 | ~14% | 25 modules, runner, cache identity, health, presets |
| `detection` | 2,887 | ~6% | Prompt, lexical, and names detectors |
| `corpus` | 2,053 | ~4% | Index, import plans, batch OCR/Analyse runs |
| `domain` | 1,901 | ~4% | Page/notebook models, dates, fingerprints, content revision |
| `config` | 1,798 | ~3% | Workspace settings, profiles, env allowlist |
| `prompt_engine` | 1,188 | ~2% | Prompt hub, render, validation |
| `declutter` | 890 | ~2% | Scanner-bed / overscan / corner-wedge crop |
| `tagging` | 608 | ~1% | Host-agnostic tag kernel + catalog store |
| `providers` | 625 | ~1% | Ollama vision client |
| `ingest` | 631 | ~1% | Stage, journal, promote |
| `page_metrics` | 543 | ~1% | Ink / blankness / hue |
| `persistence` | 281 | <1% | Locks, atomic writes, schema registry, quarantine |
| `preprocess` | 16 | <1% | Optional `gentle_contrast` only |

Physical line counts (comments and blanks included) are calibration, not the estimate. The longest modules are `ui/review_workbench.py` (1,644), `services/project.py` (1,309), `__main__.py` (1,290), `ui/run_transcribe.py` (1,234), and `ui/page_viewer.py` (1,219). The September architecture review already flags `ProjectService` and the Review workbench as concentration points. They are still the hot files.

### Declared dependencies

Runtime Python surface is small and unlocked (no lockfile; CI installs current compatible wheels):

| Extra | Packages |
|-------|----------|
| Core | Pillow, PyMuPDF, wordcloud |
| `[ui]` | Streamlit, Pydantic, ebooklib |
| `[export]` | ebooklib |
| `[dev]` | pytest, pytest-cov, pytest-timeout, ruff, plus UI extras |
| `[docs]` | Sphinx, MyST, Furo, sphinx-autobuild, mermaid, autodoc-typehints |

Ollama is an external process. Optional analysis extras (BERTopic, spaCy NER, fine-grained emotion) are **not** declared in `pyproject.toml`; missing extras degrade to `unavailable_extra`. The dependency-audit waiver log is empty.

## Shipped surface

### Everyday workflow

Sidebar order is primary (Home, Library, Search) → Workflow → View → System.

| Workflow | What a user can do |
|----------|-------------------|
| New notebook / Import | Single notebook upload, or Batch folder import with durable `ImportRun`, resume, duplicate policy |
| Transcribe | Single-model OCR or Compare models (multipass); Batch across notebooks; timeout and model-load circuits |
| Review | Scan + lanes (Transcription, Date, Tags, OCR, Cleanup, Other); disagreement queue; merged draft as a recommendation |
| Analyse | Launcher only (this notebook or Batch). Presets Quick / Balanced / Thorough / Custom |
| Detect | Poetry, lists, to-dos, quotations, beer labels, first person, swear words, names, plus custom prompts |
| Export | Markdown, text, HTML, EPUB, PDF, portable notebook JSON, fine-tune pack |

View consumes published analysis: Read, Overview, Summaries, Ask, Themes, Mood (includes Moments), People & Places. System holds Settings and Diagnostics.

CLI covers the same jobs: `init`, `import`, `models`, `run`, `multipass`, `export`, `export-finetune`, `status`, `detect`, `doctor`, `corpus-doctor`, `bulk-import`, `bulk-run`, `bulk-analyse`, `backup`, `restore`. Inventory: [docs/public_surfaces.md](../docs/public_surfaces.md).

### Analysis catalog

Twenty-five module ids are registered in `analysis/module_catalog.py`. Four require a text model (`llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary`). Heavy optional paths (`bertopic`, `semantic_similarity`, `fine_grained_emotion`, `contextual_emotion`, `entity_sentiment`, `topic_modeling`) can report unavailable rather than silently substituting. No further analysis modules are scheduled.

### Contracts and docs estate

| Estate | Count / shape |
|--------|----------------|
| Normative contracts | 26 files under `docs/contracts/` |
| Runtime guides | OCR, analysis, export, settings, install, Docker, model matrix |
| Plans | Active: usability wave, infrastructure wave, user-testing protocol. Closed plans live under `docs/archive/plans/` |
| Hosted docs | Sphinx over the Markdown corpus (`make docs`); GitHub Pages assemble (`make pages-site`, `.github/workflows/pages.yml`) |
| Reviews already on disk | Architecture-from-evidence (2026-09-03); Moments module (2026-08-19) |

The docs corpus is part of the product. Public pages were reframed in 0.8.8 so a first-time reader meets outcomes and Docker steps before contracts.

## Delivery position

Package **0.8.8**. Path recorded on the roadmap:

```text
0.8.8 (now) → 0.9.0 (U2 + I6) → 0.9-1 unfamiliar testing → 1.0 freeze → After 1.0
```

### Usability wave

| Track | Status | Meaning for this snapshot |
|-------|--------|---------------------------|
| U0 Trust | Done | Preset identity, frozen plans, shared health, export provenance |
| U1 Analyse UX | Done | Analyse is a launcher; View pages are the read models |
| U2.1 Home | Done | Empty workspace: Create + Import, plus one-line Ollama health |
| U2.3 Diagnostics | Done | System → Diagnostics runs corpus doctor; notebook doctor when one is selected |
| **U2.2 Sample notebook** | **Open** | No `samples/` tree in the repo |
| **U2.4 First-run docs acceptance** | **Still unchecked in the plan** | 0.8.8 landed Docker-preferred public docs; the usability checklist still requires a “first notebook in 15 minutes” path and a README/user-guide acceptance tick |
| U3 Daily workbench | Done | Review queue, Reading, Library covers, search filters |
| U4 Corpus | Gate green | Bulk import acceptance suite exists; richer Inbox taxonomy may continue and is not on the 0.9 critical path |

The roadmap heading “U2 — planned (not started)” is staler than Track A in the same file, which correctly marks U2.1 and U2.3 done. Track A is the accurate split.

### Infrastructure wave

| Track | Status |
|-------|--------|
| I0 Makefile + test-lane vocabulary | Done |
| I1 PR CI, Python 3.10–3.12 | Done (`.github/workflows/ci.yml`) |
| I2 Release hygiene scripts + governance | Done |
| I3 Coverage floor, pre-commit, `release-checks` | Done |
| I4 Sphinx in CI | Done |
| I5 Public landing + Pages workflow | Done (screenshot gallery still optional) |
| **I6** Nightly acceptance, Docker build in release-checks, issue templates | **Open** — no `nightly.yml`, no `.github/ISSUE_TEMPLATE`, `release-checks` stops at wheel import smoke |

`tests/README.md` still says GitHub Pages is “not in PR CI yet (I5–I6)”. Pages is a separate workflow, not a job inside `ci.yml`. That sentence is easy to misread now that I5 has landed.

### Explicitly not started

After 1.0 autobiography work (context importers, People-as-identity, Slices, reconstruction, page time-of-day) has no `data/context/` tree and must stay that way until the 1.0 freeze checklist is signed. Architecture follow-ups from the September evidence review (split `ProjectService.load` from reconcile, names detector consumes published NER only, one schema registry) are recorded as later candidates, not 0.9 work.

## Quality posture

| Gate | What it actually covers |
|------|-------------------------|
| Default pytest | Offline. Excludes `quarantined`, live Ollama, Docker, network, `slow`, `integration`, `release_only` |
| CI `tests` | Smoke, then `make test-fast` on 3.10 and 3.12; `make test-coverage` on 3.11 |
| Coverage | `.coveragerc` `fail_under = 70`, **entire `transcribe/ui` omitted**. Floor is under a historical ~85% on non-UI code |
| Lint | Ruff critical + unused on `src/transcribe`. Full Black is not a gate |
| `release-checks` | Tracked-data allowlist, secrets denylist, stale refs, root-markdown allowlist, compose loopback assert, wheel build |
| Acceptance trees | `tests/acceptance/hardening/`, `tests/acceptance/corpus/`, OCR lifecycle |

Test files by directory (134 `test_*.py`): unit 84, services 29, acceptance 11, and small lanes for ingest, export, providers, persistence, contracts, release, and one live integration probe.

The September evidence review’s test judgement still fits: strong on OCR lifecycle, fingerprints, circuits, analysis cache and crash behaviour, corpus resume, backup zip-slip, and detection. Weaker on real Streamlit behaviour (many UI tests assert source strings), encrypted-PDF rejection, disk-full during OCR, schema migration (there is no migrator), multiprocess locks, and restore killed mid-replace. UI tests that only grep for `"completed"` can encode coordinator status without proving what the operator sees; progress snapshot helpers were extracted so some of that can be tested without importing a page.

No P0 issue was evidenced for the local single-user trust model. Residual product risks that are still open from that review:

1. Cleanup failure can still seal cleanup into the OCR fingerprint while the page keeps raw text.
2. `ProjectService.load(reconcile=True)` writes (demotes interrupted attempts) on what callers treat as a read.
3. The names detector may run the NER analysis module if published NER is missing.
4. `effective_text()` is the implicit bus for analysis, detection, export, and search.
5. Archive freshness depends on callers bumping a generation token.
6. Unknown `schema_version` fails closed; there is no upgrade path. That is consistent with v1 and is a longevity limit for a corpus someone expects to open in five years.

Observability is doctor output, job records, and the progress panel. There are no metrics, traces, or a correlation id from OCR through Analyse to Detect.

## How the pieces hold together

```text
Import (declutter → PNG + journal)
  → OCR (optional Pillow preprocess → Ollama vision → optional text cleanup)
  → PageResult.effective_text()
  → Review / dates / tags
  → Analysis modules and/or detectors
  → Export, Library search, workspace ZIP
```

Jobs are in-process threads kept across Streamlit reruns. Cross-process exclusion is a file lock per notebook (OCR job lock and analysis lock). Mutations use a shorter lock and atomic replace. One OCR job and one analysis job per notebook.

That shape is coherent for a single operator. It will strain if the UI keeps absorbing workflow variants inside `review_workbench.py`, `run_transcribe.py`, and `project.py` without new module boundaries. The evidence review’s “do not” list still holds: do not replace JSON-on-disk with a database system of record, do not add an event bus, do not add v1 authentication, and do not rewrite navigation or Streamlit as a 0.9 task.

## Gaps that matter now

Ordered by what the roadmap already says blocks the next cut.

1. **Sample notebook (U2.2).** Without it, 0.9-1 testers must arrive with their own scans and a working vision model before they can see Analyse or export. The plan asks for a small fixture copied through existing init/import, analysable offline on deterministic modules.
2. **Close or re-scope U2.4.** Public docs already prefer Docker and lead with outcomes. The acceptance checkbox is still open. Either tick it against the 0.8.8 pages, or add the missing “15 minutes” path (port 8510, `HOST_PROJECTS_DIR`, Ollama model, first-run bites from known limitations) so the checkbox matches the docs.
3. **I6 sustaining lanes.** Nightly `make test-acceptance` (still offline), `docker compose build` plus `make docker-smoke` on a runner that has Docker, and issue templates. These are the remaining infra exit-gate items.
4. **Leave the rest parked.** Inbox taxonomy, architecture decoupling, reinterpretation modules, and autobiography importers are written down and should stay off the 0.9 board.

Smaller doc drift to fix when those tracks move, so the next stocktake does not have to reconcile them again:

- Roadmap section title still says U2 is “not started”.
- `tests/README.md` still groups I5 Pages with work that is not in CI.

## What this review did not do

- Did not execute `make test-fast` or `make test-coverage`. CI on `main` is the standing evidence; this note does not claim a fresh green run.
- Did not open the Streamlit app or a live Ollama host.
- Did not re-score OCR quality on real handwriting. Quality limits in [docs/known_limitations.md](../docs/known_limitations.md) remain the honesty page: model-dependent handwriting, thinking-model empty output, remote Ollama exfiltration, and analysis that inherits OCR noise.

## Related

- Product promise: [docs/PRODUCT.md](../docs/PRODUCT.md)
- Shape: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- Sequencing: [docs/ROADMAP.md](../docs/ROADMAP.md) · [docs/usability_wave_plan.md](../docs/usability_wave_plan.md) · [docs/infrastructure_wave_0_9_plan.md](../docs/infrastructure_wave_0_9_plan.md)
- Evidence review this stocktake relies on: [docs/reviews/architecture_from_evidence.md](../docs/reviews/architecture_from_evidence.md)
- Support map: [docs/public_surfaces.md](../docs/public_surfaces.md)
