# Transcribe

Transcribe is a local-first workbench for handwritten notebooks.

Import page photos or PDFs. Read them with a vision model that runs on your
computer. Correct the text beside the scan. Optionally look at themes, mood,
people, and places — then export Markdown, HTML, or a portable notebook file.

Pages stay on your machine. Transcribe does **not** send scans to a cloud OCR
service.

Not sure if this is the right tool? [What Transcribe is](docs/PRODUCT.md).

## What can I do with it?

- Turn scans into editable text
- Correct a page beside the original image
- Find themes, mood, people, and places in a notebook
- Spot poetry, lists, names, and other patterns
- Export a notebook you can keep (Markdown, HTML, EPUB, PDF)

Walkthrough: [User guide](docs/user_guide.md). Product definition: [docs/PRODUCT.md](docs/PRODUCT.md).

## On your machine

Source scans and results stay on your computer. OCR uses
[Ollama](https://ollama.com) locally. A non-local Ollama host means page images
leave this machine; the app warns and asks you to confirm.

Limits: [known limitations](docs/known_limitations.md). Third-party models: [NOTICE](NOTICE).

## From a scan to a readable notebook

You need a running Ollama server and at least one **OCR-friendly vision model**
(for example `glm-ocr` or `granite3.2-vision`). Avoid “thinking” vision tags such
as `gemma4` — they often return empty text.

1. Open the app, choose **Workflow → New notebook**, and import JPEG, PNG, or PDF pages.
2. Open **Workflow → Transcribe**, pick a vision model, and start.
3. Open **Workflow → Review** and correct the text beside the scan.
4. Optionally open **Workflow → Analyse**, keep **Balanced**, and read **View → Overview**.

Full walkthrough: [User guide](docs/user_guide.md).

Five everyday jobs: [import and transcribe](docs/user_guide.md#from-a-scan-to-a-readable-notebook), [review a page](docs/runtime/ocr.md#review-after-ocr), [analyse](docs/runtime/analysis.md), [detect patterns](docs/runtime/analysis.md#detect), [export](docs/runtime/export.md). More: [user docs sitemap](docs/USER_INDEX.md).

## Installation

**Native (recommended on the host).** Python 3.10+. Copy `.env.example` to `.env`
if you want path or Ollama overrides.

```bash
git clone https://github.com/glen-w/transcribe.git
cd transcribe
chmod +x transcribe.sh
./transcribe.sh setup         # creates .venv and installs the UI
./transcribe.sh ui            # → http://127.0.0.1:8510/
```

Point notebooks, scans, and exports outside the clone when you want data to
survive repo wipes — set `TRANSCRIBE_PROJECTS_DIR`, `TRANSCRIBE_INBOX_DIR`, and
`TRANSCRIBE_EXPORT_DIR` in `.env`.

**Docker.** Copy `.env.example` to `.env` and set **`HOST_PROJECTS_DIR`** to an
absolute path **outside this repository**.

```bash
cp .env.example .env          # set HOST_PROJECTS_DIR
docker compose up --build transcribe-web
# → http://127.0.0.1:8510/
```

Details: [installation](docs/runtime/installation.md). Docker notes: [docker](docs/runtime/docker.md). Choosing a vision model: [OCR model matrix](docs/runtime/ocr_model_matrix.md).

## Advanced and developer docs

- [User docs sitemap](docs/USER_INDEX.md) · [Docs hub](docs/index.md)
- Public landing (GitHub Pages): [website/](website/) — local assemble: `make pages-site` → `_site/`
- [Developer docs](docs/DEV_INDEX.md) · [Roadmap](docs/ROADMAP.md) · [Usability wave](docs/usability_wave_plan.md)
- [Architecture](docs/ARCHITECTURE.md) · [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · License: MIT
