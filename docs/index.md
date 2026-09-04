# Transcribe documentation

Transcribe is a local-first workbench for handwritten notebooks. You import
scans you already have, transcribe them on your machine, and keep the results.

OCR uses a local [Ollama](https://ollama.com) vision model. Transcribe does
**not** send pages to a cloud OCR service.

**See how it works:** [user guide](user_guide.md) — import scans, transcribe, review beside the page.  
**Everyday jobs:** import and transcribe, review, analyse, detect, export — [user guide](user_guide.md).  
**Is this for me?** [What Transcribe is](PRODUCT.md).  
**Privacy:** files stay on your computer; Ollama is local and off the public internet by default.

The GitHub [README](https://github.com/glen-w/transcribe#readme) is the same first-run story.

```{toctree}
:maxdepth: 2
:caption: Start here

PRODUCT
user_guide
runtime/installation
runtime/ocr
known_limitations
```

```{toctree}
:maxdepth: 2
:caption: Using Transcribe

runtime/analysis
runtime/export
runtime/settings
runtime/docker
backup_and_restore
runtime/ocr_model_recipes
runtime/ocr_model_matrix
TERMS
```

```{toctree}
:maxdepth: 1
:caption: Advanced

USER_INDEX
public_surfaces
finetune_export
CONTRACT_INDEX
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
:caption: Contracts
:glob:

contracts/*
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

## Full lists

- [User documentation sitemap](USER_INDEX.md)
- [Developer documentation index](DEV_INDEX.md)
- [Contract index](CONTRACT_INDEX.md)
- [Usability wave](usability_wave_plan.md) (active product focus)
