Type: GUIDE
Authority: docs landing hub only — indexes own their navigation tables

# Transcribe documentation

Local-first handwritten notebook OCR workbench. Start with the product definition, then installation and task guides.

Sphinx builds **this Markdown tree** (no second corpus). Archive plans stay in-repo under `docs/archive/` and are excluded from hosted navigation.

```{toctree}
:maxdepth: 2
:caption: Start here

PRODUCT
USER_INDEX
user_guide
known_limitations
runtime/installation
runtime/settings
runtime/ocr
runtime/analysis
runtime/docker
runtime/export
backup_and_restore
```

```{toctree}
:maxdepth: 2
:caption: Reference

public_surfaces
TERMS
finetune_export
CONTRACT_INDEX
```

```{toctree}
:maxdepth: 1
:caption: Contracts
:glob:

contracts/*
```

```{toctree}
:maxdepth: 1
:caption: Developers

DEV_INDEX
ROADMAP
ARCHITECTURE
developer_quickstart
usability_wave_plan
infrastructure_wave_0_9_plan
INTEGRATION_SEAM
```

```{toctree}
:maxdepth: 1
:caption: Maintainer notes
:glob:

dev/*
```

```{toctree}
:maxdepth: 1
:caption: Reviews
:glob:

reviews/*
```

## Indexes

- [User documentation index](USER_INDEX.md)
- [Developer documentation index](DEV_INDEX.md)
- [Contract index](CONTRACT_INDEX.md)
- [Archive index](archive/ARCHIVE_INDEX.md)
- [Reviews index](reviews/README.md)
- [Usability wave](usability_wave_plan.md) (active product focus)

Operational guides live under [runtime/](runtime/installation.md). Docs authority model: [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md). Surfaces map: [dev/docs_architecture.md](dev/docs_architecture.md).

Historical delivery plans are tracked under `docs/archive/` and are excluded from user navigation.
