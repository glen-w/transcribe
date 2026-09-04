# Fine-tune export

Related: [ocr-preference.md](ocr-preference.md), [notebook-export.md](notebook-export.md), product outline [../finetune_export.md](../finetune_export.md).

## Purpose

Export images + preferred/active transcriptions as a local dataset for **external** model fine-tuning. Transcribe does not train models.

## Package layout

```
finetune_export_<stamp>/
  manifest.json
  samples.jsonl
  images/<page_id>.png
  README.txt
```

- `manifest.json` format: `transcribe.finetune-export-manifest` schema_version `1`
- Knobs: `include_edited_pages`, `require_preferred`, `prefer_effective_text`, `include_rejected_candidates`, `image_mode` (`copy` \| `hardlink`)

## JSONL sample (v1)

```json
{
  "id": "<notebook_id>:<page_id>",
  "image": "images/<page_id>.png",
  "text": "<training target text>",
  "source": {
    "notebook_id": "...",
    "page_id": "...",
    "attempt_id": "...",
    "model_name": "...",
    "model_digest": "...",
    "attempt_kind": "vision|composite",
    "had_human_edit": false
  },
  "rejected": []
}
```

- Default `text`: preferred attempt `raw_text` if set, else active `raw_text`
- When `prefer_effective_text` and `edited_text` present: use effective text and set `had_human_edit=true`
- `rejected` optional list of other succeeded vision raws when `include_rejected_candidates=true`

## Privacy

Images leave the machine only if the user copies the export folder. No network upload from this export path.
