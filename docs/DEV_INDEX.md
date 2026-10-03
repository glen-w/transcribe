# Developer docs index

Active developer and maintainer docs. Historical material is listed only via [ARCHIVE_INDEX](archive/ARCHIVE_INDEX.md).

## Orientation

| Doc | Purpose |
|-----|---------|
| [developer_quickstart.md](developer_quickstart.md) | Mental model, venv, Makefile test lanes, extension points |
| [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md) | Docs authority model and sync checklist |
| [dev/docs_architecture.md](dev/docs_architecture.md) | Docs surfaces map |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System shape and ownership boundaries |
| [PRODUCT.md](PRODUCT.md) | Product definition |
| [CONTRACT_INDEX.md](CONTRACT_INDEX.md) | Concept → authoritative contract |

## Active product

| Doc | Purpose |
|-----|---------|
| [ROADMAP.md](ROADMAP.md) | Product roadmap: notebook contract through 1.0. Autobiography write-up is on file for a future separate product (scope lean 24 Sep 2026), not 1.1–2.0 |
| [usability_wave_plan.md](usability_wave_plan.md) | Usability-wave tracks U0–U4 (active; U2 open; required for 0.9.0) |
| [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md) | 0.9 infrastructure wave: **I0–I4** landed; I5–I6 remaining; required for 0.9.0 |
| [dev/release_governance.md](dev/release_governance.md) | Authoritative next-tag checklist (I2); `# pre-release` is local confidence only |
| [dev/dependency_audit.md](dev/dependency_audit.md) | CVE / waiver log |
| [dev/user_testing_0_9.md](dev/user_testing_0_9.md) | 0.9-1 unfamiliar-user testing protocol (after 0.9.0 cut) |
| [dev/smoke_kit_import_ocr.md](dev/smoke_kit_import_ocr.md) | Design only: import → OCR smoke; `edited_text` survives re-OCR. Not a PR CI vision run |
| [public_surfaces.md](public_surfaces.md) | GUI IA and supported entrypoints |
| [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) | Future notebook handoff (not shipped) |

## Reviews

Product and module reviews (critique and follow-ups — not contracts): [reviews/README.md](reviews/README.md).

## Engineering notes

| Doc | Purpose |
|-----|---------|
| [runtime/installation.md](runtime/installation.md) | Install extras and env vars |
| [runtime/docker.md](runtime/docker.md) | Container layout |
| [dev/analysis_module_porting.md](dev/analysis_module_porting.md) | TX → Transcribe dispositions (living map) |
| [dev/analysis_port_pins.md](dev/analysis_port_pins.md) | Exact TX commit/file pin registry |
| [dev/places_tx_alignment.md](dev/places_tx_alignment.md) | NER/places map alignment with TranscriptX |
| [dev/settings_tx_alignment.md](dev/settings_tx_alignment.md) | Settings / profiles / models / prompts alignment |
| [dev/ocr_review_workbench_plan.md](dev/ocr_review_workbench_plan.md) | Post-U3 OCR Review workbench (scan / tabbed lanes / evidence / merged draft / transcription) |
| [runtime/ocr_model_recipes.md](runtime/ocr_model_recipes.md) | Per-model OCR prompt recipes (DeepSeek-OCR first) |

## Archive

Historical delivery plans (Wave 1 analysis, Detection wave 2, bulk Analyse, U0/U1 hardening checklist): [archive/ARCHIVE_INDEX.md](archive/ARCHIVE_INDEX.md).

Default suite stays offline (fake Ollama provider). Live OCR probes are optional and environmental.
