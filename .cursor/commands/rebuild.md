# Docker rebuild (# rebuild)

Tear down existing containers, prune Docker build cache and images, rebuild the image, then launch using docker compose — **only when this repo has Docker packaging**.
Execute from the workspace root.

If there is no `Dockerfile` / `docker-compose.yml` yet (greenfield / local-venv-only), report that and stop after optional `# backup`; do not invent Docker assets unless the user asked.

---

## 0. Run backup first (mandatory)

Before doing anything else, run the **backup** custom command (`# backup`). Wait for it to complete, then proceed with the steps below.

---

## 1. Tear down

<!-- DISABLED: docker compose down (removes containers) - commented out after repeated data loss. -->
- **Do not run `docker compose down`** unless the user explicitly requests it. Report that tear-down is disabled for safety.
<!-- - docker compose down - DISABLED -->

---

## 2. Prune

<!-- DISABLED: All docker prune (removes images/cache) - commented out after repeated data loss. -->
- **Do not run** `docker builder prune`, `docker image prune`, or `docker system prune`. Report that prune steps are disabled for safety.
<!-- - docker builder prune -f - DISABLED -->
<!-- - docker image prune -f - DISABLED -->
<!-- - docker system prune -f - DISABLED -->

---

## 3. Build

- **Rebuild the image (no cache):** `docker compose build --no-cache` (or `docker build` if only a Dockerfile exists).
- This rebuilds the Transcribe image when defined. Do **not** bake Ollama model weights into the image; Ollama stays on the host or a separate service.

---

## 4. Launch

- Prefer documented compose service names when present (e.g. `docker compose up transcribe-ui`).
- Open the UI at **http://127.0.0.1:8510/** (Transcribe default). Never use or kill port **8501** (TranscriptX).
- Confirm Ollama reachability separately (`http://localhost:11434` or configured host).

---

## Execution rules

- Run all steps from the workspace root where `docker-compose.yml` / `Dockerfile` lives.
- After completion, confirm that the container starts and the entrypoint works.
- Never delete mounted project directories or host `projects/` data as part of rebuild.
