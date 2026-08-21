Type: PRODUCT
Authority: post-U3 OCR Review workbench sequencing; schemas stay in page-result / ocr-multipass / project-on-disk

# OCR Review workbench

**Status:** [x] landed as post-U3 deepen-in-place (not a new wave track; does not block U2 / 0.9).

**Lifecycle:** scan → independent OCR evidence → LLM merged draft → human-reviewed transcription.

## Evidence hierarchy

| Object | Role |
|--------|------|
| Scan | Source of truth |
| Raw OCR attempts (`attempt_kind=vision`) | Independent evidence |
| Merged draft (`attempt_kind=composite` internally) | LLM reconciliation of those attempts — **not a vote** |
| Transcription (`edited_text` / effective text) | Human-reviewed canonical page text |

User-facing name is **Merged draft**. JSON keeps `composite`.

Consensus (agreement %, disagreement count, n/n) uses **raw attempts only**. The editor is the resolution target. Composite may appear as “Merged draft recommends…” plus **composite departure** when it invents a reading no source has.

A composite is **current** iff its `source_attempt_ids` equal the latest succeeded vision attempt per model identity. Otherwise it is **stale**, retained, and not the live draft. Multipass regenerates when a current merged draft is missing.

**Reviewed** means the *current* effective transcription was reviewed (`reviewed_text_fingerprint` + `reviewed_evidence_fingerprint`). New OCR evidence, active-attempt change, merged-draft regen, or effective-text change → `needs_attention`. **Save** stays on the page; **Save + Mark reviewed** is atomic (persist buffer, then fingerprints, then status, then auto-advance).

Reading / Archive / Detect still use the shared page viewer. Only **Workflow → Review** is the workbench.

## Layout (Review page)

Two-pane: **scan** (left) and **tabbed review lanes** (right). Typical pass: **Transcription → Date → Tags → Other** (no scrolling past the image for date or tags).

| Tab | Purpose |
|-----|---------|
| **Transcription** | Editor, OCR evidence strip, disagreement navigation, Save / Save + Mark reviewed / Skip / Undo |
| **Date** | Manual date entry, approve/ignore suggestions (✓ / ✓✓ / ✕), regression confirm; label shows **Date ⚠** when a suggestion is pending |
| **Tags** | Page tag assignment (catalog + ad-hoc); **💾 Save tags** |
| **Other** | Notebook cover, per-notebook OCR settings (below), **Re-run OCR** (vision model; this page / all pages / not reviewed), delete page |

Nav bar **✓ date** remains for quick approve without opening the Date tab.

## OCR settings (Other tab)

Per-notebook controls (also in Compare OCR attempts and Transcribe Advanced):

- **When setting a notebook default** — prefer mode for Prefer / auto-composite: notebook default = current text (default), notebook default only (stats / fine-tune), or notebook default + current with edit gate when Transcription has an edit overlay.
- **Seed transcription from merged draft after multipass** — when on (default), a succeeded merged draft becomes active after multipass and seeds the Transcription buffer; when off, the draft remains evidence-only until you Prefer/Promote or edit.

User guide: [runtime/ocr.md](../runtime/ocr.md#notebook-ocr-settings).

## Non-goals (this slice)

Bounding boxes, per-span durable human provenance, calibrated OCR confidence, rebuilding composite as geometric merge.

## Contracts

[page-result.md](../contracts/page-result.md) · [ocr-multipass.md](../contracts/ocr-multipass.md) · [project-on-disk.md](../contracts/project-on-disk.md)
