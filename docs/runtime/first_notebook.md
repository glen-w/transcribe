# First notebook in about 15 minutes

Docker is the front door. You do not need a host Python install. You do need
[Ollama](https://ollama.com) on this computer and one OCR-friendly vision model.

The app listens on **http://127.0.0.1:8510/** (not 8501).

## 1. Ollama

Install Ollama, start it, and pull a handwriting-oriented vision tag. Examples:
`glm-ocr`, `granite3.2-vision`. Skip “thinking” vision tags such as `gemma4` —
they often return empty text.

```bash
ollama pull glm-ocr
```

## 2. Docker

Clone the repo. Copy `.env.example` to `.env`. Set **`HOST_PROJECTS_DIR`** to an
**absolute** folder **outside** the clone so wiping the repo never deletes your
notebooks.

```bash
git clone https://github.com/glen-w/transcribe.git
cd transcribe
cp .env.example .env
# edit .env: HOST_PROJECTS_DIR=/Users/you/Documents/transcribe-projects
docker compose up --build transcribe-web
```

Open **http://127.0.0.1:8510/**.

On Linux, Compose already maps `host.docker.internal` to the host so the
container can reach Ollama. If notebook files on the mount look root-owned,
run Compose with your user id:

```bash
export UID="$(id -u)"
export GID="$(id -g)"
docker compose up --build transcribe-web
```

## 3. A first notebook

In the app:

1. **Workflow → New notebook** — create one and import JPEG, PNG, or PDF pages,
   **or** click **Open sample** to copy a short placeholder notebook (text
   already filled in; OCR optional).
2. **Workflow → Transcribe** — pick the vision model you pulled, then start.
3. **Workflow → Review** — correct the text beside the scan.
4. **Workflow → Export** — Markdown or HTML is enough for a first save.

**System → Diagnostics** shows whether Ollama is reachable.

## First-run bites

- Encrypted PDFs are rejected. Use an unencrypted PDF or page images.
- Very large PDFs fail on page/byte budgets — split the file.
- Optional **Clean OCR with a text model** adds a second Ollama call per page
  and can feel slow. Leave it off until a first pass works.
- Empty OCR (`empty_output`) is a failed page, listed under Review **Failed OCR**.
  Switch to an OCR-oriented model rather than a general VLM.

More walkthrough: [User guide](../user_guide.md). Install extras and host Python:
[Installation](installation.md) (Advanced). Compose mounts: [Docker](docker.md).
Honesty list: [Known limitations](../known_limitations.md).
