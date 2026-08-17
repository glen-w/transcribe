Type: GUIDE
Authority: self

# Changelog

All notable changes to Transcribe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2026-08-17

### Added

- Maintainer **I0–I1** lanes: root `Makefile` (`test-smoke` / `test-fast` / `test-contracts` / `test-acceptance` / `docker-smoke`), [tests/README.md](tests/README.md), GitHub Actions CI (ruff critical + offline smoke/default suite on Python 3.10–3.12), compose loopback bind assert (`scripts/release/assert_compose_bind.sh`).
- Post-1.0 **autobiography workbench** sequencing on [docs/ROADMAP.md](docs/ROADMAP.md) (releases 1.1–2.0): notebook-anchored contextual evidence, Slices, cited reconstruction. Gated on 1.0. Not shipped behaviour.
- Path to **0.9.0** / **0.9-1** / **1.0** on the roadmap: U2 + I0–I6 → 0.9.0 cut → unfamiliar-user testing ([docs/dev/user_testing_0_9.md](docs/dev/user_testing_0_9.md)) → 1.0 freeze with foundation checklist for After 1.0.

### Changed

- `.[dev]` extras include pytest-cov, pytest-timeout, and ruff so CI and later coverage gates share one install.

## [0.6.5] - 2026-08-16

### Fixed

- Restore Detect knobs on analysis UI presets (`allow_detection`, `detector_ids`) so the Docker UI can import again. Thorough still includes detectors by default.

## [0.6.2] - 2026-08-16

### Added

- Planned **0.9 infrastructure wave** ([docs/infrastructure_wave_0_9_plan.md](docs/infrastructure_wave_0_9_plan.md)): CI, test lanes, release hygiene, and hosted docs, patterned on TranscriptX maintainer infra. Package stays **0.6.x** until that programme lands; then **user testing** toward **1.0**.

### Changed

- Roadmap points at archived delivery-history plans under `docs/archive/plans/` and `docs/dev/analysis_module_porting.md`.

## [0.6.1] - 2026-08-16

### Fixed

- Restore **Settings → Configuration → Backup** (create / verify / dry-run / restore via on-disk paths) and document workspace backup/restore as shipped. CLI `backup` / `restore` was never removed.

## [0.6.0] - 2026-08-15

### Added

- Organisation tagging (workspace catalogue, viewer filter, detection auto-tag).

### Changed

- Documentation organisation brought toward TranscriptX maturity: `docs/archive/` for shipped delivery plans, sectioned user/dev indexes, `docs/dev/docs_architecture.md`, deeper `docs/runtime/` task guides, root `CONTRIBUTING.md` / `SECURITY.md` / changelog.

## [0.5.0] - 2026-08

### Added

- Local-first handwritten notebook OCR workbench (Streamlit UI on port **8510**, CLI, shared services).
- Page-preserving projects, multipass OCR, Prefer/Promote, fine-tune export, Prompt Hub + Detect.
- Core notebook analysis module set with Analyse presets and View consume surfaces.
- Corpus bulk import, batch OCR, batch Analyse (acceptance gates green).
- Full-workspace backup / restore ZIP (`transcribe.workspace-backup`).

### Notes

- Pre-0.5 history is not reconstructed in this file. Product sequencing and shipped capability detail: [docs/ROADMAP.md](docs/ROADMAP.md).
