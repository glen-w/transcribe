Type: GUIDE
Authority: product outline for external fine-tuning using Transcribe exports — does not define training code

# Fine-tune export (external training)

Transcribe can export a local dataset of page images + preferred/active transcriptions for **external** fine-tuning. Training is not performed inside this project.

## What you get

Running **Export → Fine-tune dataset** (UI) or `transcribe export-finetune <project>` writes:

```
finetune_export_<stamp>/
  manifest.json       # knobs, counts, model stats
  samples.jsonl       # one JSON object per included page
  images/<page_id>.png
  README.txt
```

Contract detail: [contracts/finetune-export.md](contracts/finetune-export.md).

## Typical external workflow

1. Prefer OCR attempts in Review (or rely on active / human edits per export knobs).
2. Export the fine-tune package from Transcribe.
3. Train a vision–language model elsewhere (examples: Unsloth, Hugging Face TRL, Ollama create/Modelfile flows, or any SFT tool that accepts image+text JSONL).
4. Install the resulting model into your local Ollama (or other runtime).
5. Select that model in Transcribe for future OCR runs.
6. Optionally use multipass compare to verify quality against your previous models.

## Privacy

Images and text stay on disk in the export folder. They leave the machine only if **you** copy or upload that folder to a training environment.

## Knobs

| Knob | Effect |
|------|--------|
| Prefer effective text | Use human `edited_text` when present |
| Require preferred | Skip pages without `preferred_attempt_id` |
| Include rejected | Attach other vision candidates for preference/DPO-style training |
| Image mode | `copy` or `hardlink` of active page renders |

## Non-goals

- No training loop, GPU job, or weight upload inside Transcribe
- No cloud fine-tune API integration
