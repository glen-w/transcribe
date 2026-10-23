# Transcribe vs TranscriptX assessments

Snapshot date: **2026-10-23**.

These notes compare Transcribe (this repo) with the sibling product TranscriptX. They are a **maintainer survey**, not product contracts. Behaviour still lives in [CONTRACT_INDEX.md](../CONTRACT_INDEX.md). Sequencing still lives in [ROADMAP.md](../ROADMAP.md).

| Pin | Value |
|-----|--------|
| Transcribe | package **0.8.8**, latest tag `v0.8.8`, branch `main` at survey time |
| TranscriptX | package **1.0.1**, tags `v1.0.0` / `v1.0.1`, HEAD about 13 commits ahead of `v1.0.1` |
| Root `assessments/` | gitignored local run logs in both repos — **not** this folder |

## How to read

| Doc | Use |
|-----|-----|
| [2026-10-23-transcribe.md](2026-10-23-transcribe.md) | What this notebook workbench already shipped at survey (package 0.8.8); U2/I6/1.0 landed afterwards |
| [2026-10-23-transcriptx.md](2026-10-23-transcriptx.md) | What the audio product shipped for public 1.0 (patterns to copy vs audio-only) |
| [2026-10-23-drift.md](2026-10-23-drift.md) | Shared patterns, naming pairs, and gap severity |
| [2026-10-23-v1-gap-register.md](2026-10-23-v1-gap-register.md) | Execution checklist for the v1 wave programme |

The lag is **release maturity**, not a missing audio stack. Transcribe must not import TranscriptX. Do not edit the TranscriptX tree from this programme.

## Related

- Product boundary: [PRODUCT.md](../PRODUCT.md)
- Path to 0.9.0 / 1.0: [ROADMAP.md](../ROADMAP.md#path-to-090--10)
- Usability U2: [usability_wave_plan.md](../usability_wave_plan.md)
- Infra I0–I6: [infrastructure_wave_0_9_plan.md](../infrastructure_wave_0_9_plan.md)
- Future file handoff: [INTEGRATION_SEAM.md](../INTEGRATION_SEAM.md)
