# Manual acceptance suite (1.0) — maintainer runbook

**Status:** executable kit for a **1.0** freeze pass  
**Related:** [release_severity_triage.md](release_severity_triage.md), [install_verification_matrix.md](../runtime/install_verification_matrix.md), [first_notebook.md](../runtime/first_notebook.md), [known_limitations.md](../known_limitations.md)

Authoritative **maintainer** acceptance checklist for the notebook workbench.
Automated pytest is complementary, not a substitute. **0.9.0** still keys off
U2 + I6; this runbook joins the **1.0** checklist in
[release_governance.md](release_governance.md).

Offline steps are written so CI / `# light-test` can cover them. Live OCR is a
human / `# deep-test` step and is **`skipped`** when Ollama is down — never a
silent pass.

---

## 0. Prerequisites

| Check | Criterion |
|-------|-----------|
| Candidate identity | Record package version + exact git SHA |
| Clean worktree intent | Prefer a tagged/candidate commit; note dirty files |
| Disposable data root | Do not contaminate a production projects dir |
| Install profile | Docker Compose (recommended) and/or native as claimed |
| Streamlit | Record `streamlit.__version__` for the profile under test |

---

## 1. Journey classification

| Class | Rule |
|-------|------|
| **required** | Must pass for this profile, or 1.0 is blocked |
| **conditional** | Required when the profile claims the capability (live OCR, native GUI) |
| **optional** | Strongly expected when practical; skip needs reason + severity |

Skipping a **required** journey needs: skip rationale, severity, and evidence.

---

## 2. Ordered journeys

### 2.1 Installation and launch — **required**

- Install / launch UI per chosen profile on port **8510** (never 8501).
- Home loads without traceback.

**Offline:** `python -c "import transcribe; print(transcribe.__version__)"` plus
`make test-smoke` on the SHA. **Live UI:** Docker or `./transcribe.sh ui`.

### 2.2 Import or Open sample — **required**

- **Offline:** **New notebook → Open sample**, or import
  `tests/fixtures/mini_page.png` with the fake `VisionOCRProvider`.
- Library / notebook list shows the new notebook.

Do not require live Ollama for this journey.

### 2.3 Transcribe or pre-seeded text — **required** (one of)

| Path | When | Class |
|------|------|-------|
| Pre-seeded `edited_text` (sample notebook) | Always available offline | required |
| Fake vision provider on `mini_page.png` | Default suite / light-test | required (offline) |
| Live Ollama vision OCR | Human / deep-test | **conditional** — skip if daemon or vision tag is missing |

Live OCR skip is `skipped (Ollama down)`, not a pass.

### 2.4 Review correction survives — **required** (offline)

- Edit a page’s `edited_text` in Review.
- Re-run OCR (fake or live) and confirm the human edit is still the published text.
- Contract: notebook identity, original scans, and human edits survive re-OCR.

Covered in the default suite; record the pytest node id when using tests as evidence.

### 2.5 Analyse Quick — **required** (offline)

- Run Analyse **Quick** (no text LLM, no heavy modules) on the sample or mini notebook.
- Overview opens without crash. Missing optional extras (`bertopic`) stay
  `unavailable_extra`, not a silent substitute.

### 2.6 Export — **required** (offline)

- Export Markdown (or HTML) of the notebook.
- Ignored pages stay omitted from reading formats when the export toggle is on
  (Reader hide-ignored is a separate wave; export already omits `ignored`).

### 2.7 Backup verify — **required** (offline)

- `transcribe backup create` then `transcribe backup verify <archive.zip>`.
- Schema bumps that Transcribe cannot load **refuse** with a clear message;
  recover via backup ([backup_and_restore.md](../backup_and_restore.md)).

### 2.8 Failure recovery — **required** (at least two cases)

| Case | Expected | Severity if broken |
|------|----------|--------------------|
| Missing Ollama when a vision/text module is selected | Clear message; no silent hang | must-fix |
| Fake provider / mini_page import of a missing path | Rejected; no corrupt index | must-fix / blocker |
| Optional BERTopic extra absent | `unavailable_extra`; pipeline continues | must-fix |
| Cancelled OCR job | Cancel acknowledged; no corrupt half-commit | must-fix |

Exercise ≥2 cases. Offline suite already covers several; live missing-Ollama is
conditional.

---

## 3. Environments

| Env | Notes |
|-----|-------|
| Docker Compose (recommended) | Port **8510**, loopback bind, host Ollama |
| Native (if claiming support) | `./transcribe.sh`; same port |

---

## 4. Evidence table

Copy one row per journey:

| Field | Value |
|-------|-------|
| environment | Docker / native |
| package version | |
| SHA | |
| date | |
| journey id | e.g. 2.3 live OCR |
| class | required / conditional / optional |
| outcome | pass / fail / skip |
| skip rationale | required if skip |
| severity | blocker / must-fix / known limitation / post-1.0 / — |
| evidence link | pytest node id, log path, or ticket |
