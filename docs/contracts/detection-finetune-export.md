# Detection fine-tune export

Related: [finetune-export.md](finetune-export.md), [detection-finding.md](detection-finding.md),
product outline [../finetune_export.md](../finetune_export.md).

## Purpose

Export page images + effective text with **approved / rejected** detection
finding labels as a local dataset for **external** detector fine-tuning.
Transcribe does not train models.

## Package layout

```
detection_finetune_export_<stamp>/
  manifest.json
  samples.jsonl
  images/<page_id>.png
  README.txt
```

- `manifest.json` format: `transcribe.detection-finetune-export-manifest` schema_version `1`
- Knobs: `include_unreviewed` (default false), `detector_ids`, `finding_types`, `image_mode` (`copy` \| `hardlink`)

## JSONL sample (v1)

```json
{
  "id": "<notebook_id>:<finding_id>",
  "image": "images/<page_id>.png",
  "text": "<page effective text>",
  "label": "approved|rejected|unreviewed",
  "finding": {
    "finding_id": "...",
    "detector_id": "...",
    "finding_type": "...",
    "snippets": [],
    "prompt_id": "...",
    "prompt_version": "..."
  },
  "source": {
    "notebook_id": "...",
    "page_id": "..."
  }
}
```

Unreviewed findings are excluded by default. Filter by `detector_id` /
`finding_type` via CLI flags or options.

## Surfaces

- CLI: `transcribe export-detection-finetune <project> [dest]`
- UI: Workflow → Export → **Detection fine-tune**

## Privacy

Images leave the machine only if the user copies the export folder. No network
upload from this export path.
