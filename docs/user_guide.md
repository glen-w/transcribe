# User guide

Import scans → transcribe with a local vision model → correct the text beside
the page → optionally analyse → export.

Product framing: [PRODUCT.md](PRODUCT.md). This page is the golden path in the
UI. CLI one-liners sit under each step; flags and batch jobs live in the
runtime guides.

## From a scan to a readable notebook

1. Create a notebook: **Workflow → New notebook**.
2. Import JPEG, PNG, or PDF pages: **Workflow → Import**.
3. Transcribe: **Workflow → Transcribe**, pick an OCR-friendly vision model, start.
4. Correct: **Workflow → Review**, fix the text beside the scan.

Then, if you want themes and summaries: **Workflow → Analyse** with **Balanced**,
then **View → Overview**.

## Common workflows

| Job | Where |
|-----|--------|
| Import and transcribe a notebook | This page, then [OCR](runtime/ocr.md) |
| Review and correct a page | [OCR — Review](runtime/ocr.md#review-after-ocr) |
| Analyse a notebook | [Analysis](runtime/analysis.md) |
| Detect poetry, lists, names, … | [Detect](runtime/analysis.md#detect) |
| Export Markdown / HTML / PDF | [Export](runtime/export.md) |

## 1. Create or open a notebook

**UI:** pick an existing notebook from the sidebar, or **Workflow → New notebook**.
First visit opens **Home**. Rename later from **Library** or **Workflow → Import**.

**CLI:**

```bash
./transcribe.sh cli init "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --title "Travel 2024"
```

On-disk layout: [contracts/project-on-disk.md](contracts/project-on-disk.md).

## 2. Import

Supported inputs: JPEG, PNG, PDF (unencrypted). PDFs become one PNG per page.

**UI:** select a notebook → **Workflow → Import** → Target **This notebook** →
upload → Import files. A live panel shows per-file status.

Visual declutter (scanner-border crop) defaults **on**. Toggle or re-apply under
**Settings → Configuration → Import** (does not re-run OCR).

**CLI:**

```bash
./transcribe.sh cli import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./scan.pdf --dpi 200
```

Several folders at once: [Bulk import](#bulk-import-and-batch-jobs).

## 3. Transcribe

You need a running Ollama server and an OCR-friendly **vision** model. Prefer
OCR-oriented tags over general VLMs. Thinking models such as `gemma4` are hidden
from the picker because they often return empty text.

**UI:** **Workflow → Transcribe** → Target **This notebook** → choose a vision
model → optional **Clean OCR with a text model** → Start transcription. Open
**Model information** under the picker for size and OCR-fit notes.

Jobs show live per-page progress. After repeated timeouts or a model that will
not load, remaining pages for **that** model are skipped so a bad tag does not
burn the whole notebook.

**CLI:**

```bash
./transcribe.sh cli models
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model glm-ocr
```

Compare two models, or transcribe many notebooks: [OCR](runtime/ocr.md).
Caveats: [known limitations](known_limitations.md) · [model matrix](runtime/ocr_model_matrix.md).

## 4. Review

**Review** is the work queue for the open notebook: scan on the left, one lane
at a time on the right (**Transcription**, **Date**, **Tags**, **OCR**,
**Cleanup**, **Other**).

Approve or edit the text, then **Save + Mark reviewed** to move on. **Reading**
is the same pages in chronological order, read-only. **Library** is the cover
gallery; **Search** finds text across notebooks.

Workbench detail, keyboard shortcuts, and re-run OCR: [OCR — Review](runtime/ocr.md#review-after-ocr).

```bash
./transcribe.sh cli status "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

## 5. Analyse (optional)

After pages have text, open **Workflow → Analyse**:

1. Choose **Quick** / **Balanced** / **Thorough** / **Custom**. First-time: keep **Balanced**.
2. Optionally add an Ask-notebook question.
3. Run analysis. On success, open **View → Overview**.

**View** pages (Overview, Themes, Mood, Summaries, People & Places) show charts
and lists, not raw JSON. Mood includes **Moments**; Summaries includes **Ask**.
**Jump to page** opens that page in Reading.

**View → Detect** scans for poetry, lists, quotations, names, and similar.
Accept or reject findings; accepted findings can apply page tags.

Need a **text** Ollama model for LLM modules. Deterministic modules work without
one. Presets, batch Analyse, and detector lists: [analysis](runtime/analysis.md).

## 6. Export

**UI:** **Workflow → Export** — pick formats and typography.

Produces JSON, Markdown, plain text, HTML, EPUB, and/or PDF.

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

Formats, anthology, and fine-tune packages: [export](runtime/export.md).

## Integrity, backup, and settings

- **System → Diagnostics** — workspace health, and notebook health when one is selected.
- **Settings → Configuration → Backup** — full-workspace ZIP. Guide: [backup and restore](backup_and_restore.md).
- **Settings** tabs: Configuration · Analysis · Detection · Tags · Prompts · Interface · Models · Profiles · Export. [Settings](runtime/settings.md).

```bash
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli backup create
```

## Bulk import and batch jobs

Everyday use is one notebook at a time. To ingest a folder of scans, or many
folders as many notebooks: **Workflow → Import** → Target **Batch**. After a
successful import, **Transcribe imported notebooks** opens batch OCR.

**Workflow → Analyse → Batch** runs analysis across a list of notebooks.

Docker users paste **container** paths (`/mnt/inbox`), not host paths.
Details: [docker](runtime/docker.md) · CLI: [public surfaces](public_surfaces.md).

## Privacy

Prefer loopback Ollama (`http://localhost:11434`). A remote host sends page
images off-machine and requires acknowledgement. See [known limitations](known_limitations.md).
