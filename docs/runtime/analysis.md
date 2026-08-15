Type: GUIDE
Authority: Analyse / Detect / View operations — summarizes analysis and detection contracts; does not redefine schemas

# Analysis and Detect

Run notebook analysis on transcribed text, consume results under **View**, and scan for phenomena with Detect. Product framing: [PRODUCT.md](../PRODUCT.md). Entrypoints / IA: [public_surfaces.md](../public_surfaces.md). Limits: [known_limitations.md](../known_limitations.md).

**Contracts:** [analysis-document](../contracts/analysis-document.md) · [analysis-result](../contracts/analysis-result.md) · [analysis-run-storage](../contracts/analysis-run-storage.md) · [analysis-batch-run](../contracts/analysis-batch-run.md) · [notebook-eligibility](../contracts/notebook-eligibility.md) · detection contracts via [CONTRACT_INDEX](../CONTRACT_INDEX.md).

## This notebook Analyse

**UI:** **Workflow → Analyse**

1. Choose a preset (**Quick** / **Balanced** / **Thorough** / **Custom**).
2. Optionally enable an Ask-notebook question.
3. Run analysis. On success, open **View → Overview** (or **Detect** when the plan is detector-only).

| Preset | Includes (summary) |
|--------|-------------------|
| **Quick** | Light/medium only — no LLM, no heavy modules, no detectors |
| **Balanced** | Adds `semantic_similarity` + `llm_summary` |
| **Thorough** | All suitable core modules (including heavy + LLM suite) + all detectors |
| **Custom** | Pick modules and detectors (modules seeded from Balanced) |

Detectors freeze into `AnalysisRunPlan.detector_ids` and run via `DetectionService` **after** modules (not as analysis modules). Use a **text** Ollama model for LLM modules and detectors (workspace default under **Settings → Models**, per-notebook Analyse, or Batch pick). Deterministic synthesis works without it. Missing model/extras surface as plain capability messages (for example “Needs a text model”).

Edit preset policies under **Settings → Analysis**. Mid-run settings changes apply to the **next** run only.

## View consume

Inspect published results under **View**: Overview / Themes / Mood / Summaries. Themes includes **People**; Mood includes **Moments**; Summaries includes **Ask**. A shared status strip shows whether results are current.

- Overview / Mood: **Compare with corpus / period** for numeric metrics vs other notebooks
- Mood → Moments and page-series charts: **Jump to page** → Reading
- **Places** (primary nav): map of places across notebooks (opt-in geocoding)
- Technical module details under **Advanced**

Chart compare notes: [dev/analysis_visual_compare.md](../dev/analysis_visual_compare.md).

## Detect

**UI:** **View → Detect** — review findings from suite runs (approve/reject, jump to source pages). Ad-hoc / page-scoped runs still launch from **Detect → Run Detection**.

Built-ins: poetry, to-do lists, lists, quotations, beer labels, plus custom detectors.

```bash
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --detector poetry
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --detector poetry --auto-tag
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --list
```

Check **Tag matching pages** (or **Apply tags from findings**) to union the detector’s tag onto span pages; rejected findings are skipped. `--auto-tag` / Detection auto-tag defaults do **not** enter detector cache identity. Catalogue contract: [tag-catalog](../contracts/tag-catalog.md).

Manage prompts under **Settings → Prompts**; custom detectors and auto-tag defaults under **Settings → Detection**; labels/colours/merge under **Settings → Tags**.

## Batch Analyse

```bash
./transcribe.sh cli bulk-analyse pending|import-run|notebooks --preset balanced
./transcribe.sh cli bulk-analyse status|resume <analysis_batch_id>
```

**UI:** **Workflow → Analyse → Batch** — pick notebooks, preset, optional shared text model (when the plan includes LLM modules or detectors), **Start batch analysis**. Dual progress (notebooks + steps: modules then detectors). Empty-text notebooks are skipped. Orchestration only — publish stays per-notebook ([analysis-batch-run](../contracts/analysis-batch-run.md)).

## Related

- Settings / presets: [settings.md](settings.md)
- OCR first: [ocr.md](ocr.md)
- Golden path: [user_guide.md](../user_guide.md)
- Roadmap / focus: [ROADMAP.md](../ROADMAP.md) · [usability_wave_plan.md](../usability_wave_plan.md)
