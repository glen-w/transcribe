# Analysis and Detect

Run analysis on transcribed text, read the results under **View**, and scan for
patterns with Detect.

First-time path: [user guide](../user_guide.md). Limits:
[known limitations](../known_limitations.md).

## This notebook

**UI:** **Workflow → Analyse**

1. Choose a preset (**Quick** / **Balanced** / **Thorough** / **Custom**). First-time: keep **Balanced**.
2. Optionally enable an Ask-notebook question.
3. Run analysis. On success, open **View → Overview**.

| Preset | What you get |
|--------|----------------|
| **Quick** | Fast lexical / structural modules — no LLM, no heavy modules, no detectors |
| **Balanced** | Adds similarity clustering and an LLM summary |
| **Thorough** | All suitable core modules plus every detector |
| **Custom** | Pick modules and detectors (starts from Balanced) |

Use a **text** Ollama model for LLM modules and detectors (**Settings → Models**,
or pick one on Analyse / Batch). Deterministic modules work without it. Missing
pieces show as plain messages such as “Needs a text model”.

Edit what each preset includes under **Settings → Analysis**. Mid-run settings
changes apply to the **next** run only.

## View

Inspect results under **View**: Overview / Themes / Mood / Summaries /
People & Places. Mood includes **Moments**; Summaries includes **Ask**. A status
strip shows whether results are current.

- Overview / Mood: **Compare with corpus / period** against other notebooks
- Mood → Moments and page-series charts: **Jump to page** → Reading
- **People & Places**: This notebook | All notebooks (opt-in map geocoding)
- Technical module details under **Advanced** (enable in **Settings → Configuration → Overview**)

Chart notes: [visual compare](../dev/analysis_visual_compare.md).

## Detect

**UI:** **View → Detect** — review findings (**Accept** / **Reject**, jump to
source pages). Accept applies remaining page tags. Multi-page findings add
per-page Accept / Reject; **Accept remaining** keeps the others.

Built-ins: poetry, to-do lists, other lists, quotations, beer labels,
first-person `I` counts, swear-word counts, **names / people**, plus custom
detectors. Count detectors show a per-page table instead of review cards.

Ad-hoc runs still launch from **Detect → Run Detection**.

```bash
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --detector poetry
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --list
```

**Tag matching pages** unions tags onto span pages; rejected findings are
skipped. **Names / people** tags each detected person name rather than a generic
`names` tag.

Manage prompts under **Settings → Prompts**; custom detectors under
**Settings → Detection**; labels under **Settings → Tags**.

## Batch Analyse

**UI:** **Workflow → Analyse → Batch** — pick notebooks, a preset, optional
shared text model, **Start batch analysis**. Empty-text notebooks are skipped.

```bash
./transcribe.sh cli bulk-analyse pending|import-run|notebooks --preset balanced
./transcribe.sh cli bulk-analyse status|resume <analysis_batch_id>
```

## Related

- Settings / presets: [settings.md](settings.md)
- OCR first: [ocr.md](ocr.md)
- Golden path: [user_guide.md](../user_guide.md)
- Roadmap: [ROADMAP.md](../ROADMAP.md) · [usability wave](../usability_wave_plan.md)
- Contracts: [CONTRACT_INDEX.md](../CONTRACT_INDEX.md) (analysis-* and detection-*)
