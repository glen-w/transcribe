# Restart Streamlit app (# streamlit)

Kill any Transcribe Streamlit process on **port 8510** and start the Transcribe OCR UI.

**Port policy:** Transcribe always uses **8510**. Never use or kill **8501** — that is TranscriptX's default port and must remain undisturbed while developing both projects side by side.

Execute from the workspace root.

---

## 1. Kill existing Transcribe UI only

- Find the process using port **8510** (e.g. `lsof -i :8510` or `lsof -ti :8510`).
- Kill that process only (e.g. `kill $(lsof -ti :8510)`).
- Confirm port 8510 is free.
- **Do not** inspect, kill, or bind port 8501.

---

## 2. Start the UI

```bash
streamlit run src/transcribe/ui/app.py --server.headless true --server.port 8510
```

Project `.streamlit/config.toml` also defaults `server.port` to 8510 so a bare `streamlit run` stays off 8501.

Run in the background. This starts the thin Streamlit client (Home / Import / Setup / Run / Review / Export). Core OCR logic must stay in services, not widgets.

---

## 3. Verify

- Optionally check: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8510/` (expect 200).
- Report that the app is running at **http://127.0.0.1:8510/**.
- Note: Ollama itself is separate (`http://localhost:11434` by default); Streamlit up does not imply a vision model is loaded.

---

## Execution rules

- Run from the workspace root.
- Always use port **8510** for Transcribe.
- Never kill or start anything on port **8501** (TranscriptX).
- Do not start a second Transcribe instance on 8510 if one is already running; kill the existing 8510 process first.
- Do not import or run OCR/provider code from ad-hoc Streamlit snippets; use the app entrypoint.
