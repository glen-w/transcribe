Type: GUIDE
Authority: curated navigation only — does not own product rules or contracts

# User docs index

Curated entry points for people using Transcribe (not repository historians).

## Start here

| Doc | Purpose |
|-----|---------|
| [README.md](../README.md) | Product landing and quickstart |
| [PRODUCT.md](PRODUCT.md) | What Transcribe is and is not |
| [user_guide.md](user_guide.md) | Golden path: import → OCR → review → analyse → export |
| [Installation](runtime/installation.md) | Local install, extras, environment |
| [Docker](runtime/docker.md) | Compose mounts and Ollama from Docker |
| [Settings & knobs](runtime/settings.md) | Configuration scopes, profiles, UI knobs |
| [OCR / transcription](runtime/ocr.md) | Single-run, multipass, batch, cleanup |
| [Analysis & Detect](runtime/analysis.md) | Analyse presets, View consume, Detect |
| [Export](runtime/export.md) | Notebook formats, anthology, fine-tune pointer |
| [Backup & restore](backup_and_restore.md) | Full-workspace ZIP create / verify / restore |
| [Known limitations](known_limitations.md) | Public honesty page |

## Reference

| Doc | Purpose |
|-----|---------|
| [Public surfaces](public_surfaces.md) | Supported CLI / UI / scripts |
| [Terminology](TERMS.md) | Non-authoritative glossary → contracts |
| [Fine-tune export](finetune_export.md) | Product outline for external training |
| [Roadmap](ROADMAP.md) | Product priorities (0.8.0 → 0.9.0 → 0.9-1 testing → 1.0; After 1.0 autobiography planned) |
| [Usability wave](usability_wave_plan.md) | Active product focus: U0–U4 (U2 required for 0.9.0) |

## Contracts (rules, not tutorials)

Prefer the [Contract index](CONTRACT_INDEX.md) for invariants. Key user-visible contracts:

- [Public surfaces](public_surfaces.md)
- [Project on disk](contracts/project-on-disk.md)
- [Page results](contracts/page-result.md)
- [Notebook export](contracts/notebook-export.md)
- [Workspace settings](contracts/workspace-settings.md)
- [Workspace backup](contracts/workspace-backup.md)

## Not in this index

Developer plans, inventories, and historical archives live under [DEV_INDEX.md](DEV_INDEX.md) and [archive/ARCHIVE_INDEX.md](archive/ARCHIVE_INDEX.md).

Start here if you are new: [../README.md](../README.md) → [user_guide.md](user_guide.md).
