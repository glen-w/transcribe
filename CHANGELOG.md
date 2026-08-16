Type: GUIDE
Authority: self

# Changelog

All notable changes to Transcribe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
