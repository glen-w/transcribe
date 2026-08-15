Type: GUIDE
Authority: self

# Changelog

All notable changes to Transcribe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Documentation organisation brought toward TranscriptX maturity: `docs/archive/` for shipped delivery plans, sectioned user/dev indexes, `docs/dev/docs_architecture.md`, deeper `docs/runtime/` task guides (settings / OCR / analysis / export), root `CONTRIBUTING.md` / `SECURITY.md` / this changelog. No workflow walkthroughs or Sphinx hosting in this pass.

## [0.5.0] - 2026-08

### Added

- Local-first handwritten notebook OCR workbench (Streamlit UI on port **8510**, CLI, shared services).
- Page-preserving projects, multipass OCR, Prefer/Promote, fine-tune export, Prompt Hub + Detect.
- Core notebook analysis module set with Analyse presets and View consume surfaces.
- Corpus bulk import, batch OCR, batch Analyse (acceptance gates green).
- Full-workspace backup / restore ZIP (`transcribe.workspace-backup`).

### Notes

- Pre-0.5 history is not reconstructed in this file. Product sequencing and shipped capability detail: [docs/ROADMAP.md](docs/ROADMAP.md).
