Type: GUIDE
Authority: user flows and examples — summarizes contracts; does not define schemas

# User guide

Import pages → run local OCR → review/edit → analyse → export. Product framing: [PRODUCT.md](PRODUCT.md). Entrypoints: [public_surfaces.md](public_surfaces.md).

Task detail lives in runtime guides: [installation](runtime/installation.md) · [settings](runtime/settings.md) · [ocr](runtime/ocr.md) · [analysis](runtime/analysis.md) · [export](runtime/export.md) · [docker](runtime/docker.md).

## 1. Create or open a notebook

**UI:** pick an existing notebook from the sidebar **View** picker (sets context for Workflow and View pages), or choose **Workflow → New notebook**, name it, and create. Rename later from **Library** (Rename action) or **Workflow → Import**. First visit opens **Home**.

**CLI:**

```bash
./transcribe.sh cli init "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --title "Travel 2024"
```

On-disk layout summary: [contracts/project-on-disk.md](contracts/project-on-disk.md).

## 2. Import

Supported inputs: JPEG, PNG, PDF (unencrypted). PDFs are rendered to per-page PNGs.

```bash
./transcribe.sh cli import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./scan.pdf --dpi 200
```

In the UI: select a notebook → **Workflow → Import** → Target **This notebook** → set **Notebook name** if needed → upload → Import files. A live progress panel shows per-file status.

**Visual declutter** (scanner-border crop) defaults **on** for imports. Toggle and **re-apply** under **Settings → Configuration → Import** (does not re-run OCR) — [settings.md](runtime/settings.md).

## 3. Choose a vision model and run

```bash
./transcribe.sh cli models
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
```

**UI:** **Workflow → Transcribe** → This notebook (or Compare models for multipass). Prefer OCR-oriented vision tags. Full single-run / multipass / batch detail: [runtime/ocr.md](runtime/ocr.md). Caveats: [known_limitations.md](known_limitations.md).

## 4. Review, Reading, and search

**Review** is a needs-attention queue for the open notebook (dates, empty text, OCR failures). Prefer / Promote when multiple attempts exist; edits live in `edited_text`. **Reading** is chronological image + read-only text. **Archive** / **Search** span the workspace.

```bash
./transcribe.sh cli status "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

Preference stats: `transcribe models --prefs` — [ocr-preference](contracts/ocr-preference.md).

## 5. Notebook analysis (optional)

**Workflow → Analyse** with Quick / Balanced / Thorough / Custom, then consume under **View** (Overview / Themes / Mood / Summaries). **View → Detect** for poetry, lists, quotations, beer labels, and custom detectors. Batch Analyse under **Workflow → Analyse → Batch**.

Detail: [runtime/analysis.md](runtime/analysis.md). Roadmap: [ROADMAP.md](ROADMAP.md).

## 6. Export

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

**UI:** **Workflow → Export**. Formats, anthology, typography: [runtime/export.md](runtime/export.md).

## 7. Integrity check

```bash
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --deep
```

**UI:** **System → Diagnostics**.

## 8. Workspace backup / restore

Pack notebooks + corpus + config into a ZIP, then replace-restore onto current mounts. Operator guide: [backup_and_restore.md](backup_and_restore.md).

```bash
./transcribe.sh cli backup create
./transcribe.sh cli backup verify /path/to/workspace.zip
./transcribe.sh cli restore /path/to/workspace.zip --yes
```

## 9. Bulk import, batch OCR, and bulk Analyse

Corpus bulk import is **supported** ([corpus-integrity](contracts/corpus-integrity.md) acceptance gate green). Single-file import (§2) remains the everyday path.

**UI:** **Workflow → Import → Batch** (legacy Inbox). After import, **Transcribe imported notebooks** opens **Transcribe → Batch**. **Analyse → Batch** for multi-notebook Analyse.

**Docker:** paste **container** paths (`/mnt/inbox`, `/mnt/notebooks`) — [runtime/docker.md](runtime/docker.md#bulk-import-paths-inbox-ui--cli-in-docker).

```bash
./transcribe.sh cli bulk-import folder ./scans --policy skip_existing_v1
./transcribe.sh cli bulk-import folders ./scan-batches --on-existing skip
./transcribe.sh cli bulk-run pending --model llama3.2-vision
./transcribe.sh cli corpus-doctor --deep
```

OCR batch detail: [runtime/ocr.md](runtime/ocr.md). Analyse batch detail: [runtime/analysis.md](runtime/analysis.md).

## Privacy reminder

Prefer loopback Ollama. Remote hosts send page images off-machine and require acknowledgement. See [known_limitations.md](known_limitations.md) · [SECURITY.md](../SECURITY.md).
