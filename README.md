# Transcribe

Local-first handwritten notebook OCR using [Ollama](https://ollama.com) vision models.

Import JPEG/PNG/PDF pages into a project directory, transcribe with a locally hosted vision model, review and correct side-by-side, then export Markdown/plain text plus a portable `transcribe.notebook` JSON artifact.

## Requirements

- Python 3.10+
- A running Ollama server with at least one vision-capable model
- Optional: Streamlit UI (`pip install 'transcribe[ui]'`)

## Install

```bash
cd /Users/89298/Documents/transcribe
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## CLI quick start

```bash
# Create a project and import an image
python -m transcribe init ./my-notebook
python -m transcribe import ./my-notebook ./page.jpg
python -m transcribe models          # list vision models from local Ollama
python -m transcribe run ./my-notebook --model llama3.2-vision
python -m transcribe export ./my-notebook ./exports
```

## Streamlit UI

Runs on **port 8510** by default (`.streamlit/config.toml`) so it does not collide with TranscriptX on 8501.

```bash
streamlit run src/transcribe/ui/app.py
# → http://127.0.0.1:8510/
```

## Privacy

By default Transcribe talks to `http://localhost:11434`. Configuring a non-loopback Ollama host means page images leave this machine; the UI/CLI will warn and require acknowledgement.

## Design notes

- Page-preserving project format (`transcribe.project` + per-page `transcribe.page-result`)
- Portable interchange export (`transcribe.notebook`) with no required absolute paths
- Content fingerprints for skip/resume; immutable OCR attempts; human edits in `edited_text`
- No cloud providers; no TranscriptX dependency (future seam documented in `docs/INTEGRATION_SEAM.md`)

## License

MIT. See `NOTICE` for third-party attributions.
