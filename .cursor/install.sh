#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Transcribe.
# Safe to run repeatedly: recreates only what is missing.
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. System packages: venv support + zstd (required by the Ollama installer).
if ! dpkg -s python3.12-venv >/dev/null 2>&1 || ! command -v zstd >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv zstd
fi

# 2. Project virtualenv + editable install with dev extras (pytest + Streamlit UI).
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e '.[dev]' -q

# 3. Ollama: local vision-model server that powers real OCR.
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

# 4. Pull the default vision model if absent. `ollama pull` needs a running
#    server, so start a transient one, pull, then stop it (nothing lingers).
MODEL="gemma3:4b"
if ! ollama list 2>/dev/null | grep -q "^${MODEL}"; then
  ollama serve >/tmp/ollama-install.log 2>&1 &
  OLLAMA_PID=$!
  for _ in $(seq 1 30); do
    curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
  ollama pull "$MODEL"
  kill "$OLLAMA_PID" 2>/dev/null || true
  wait "$OLLAMA_PID" 2>/dev/null || true
fi

echo "Transcribe install complete."
