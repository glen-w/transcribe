#!/usr/bin/env bash
# I6: build the Compose image and assert bind. Skip (exit 0) when Docker is missing.
# Does not start the UI and does not publish port 8510.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: docker not available"
  exit 0
fi

if [[ -z "${HOST_PROJECTS_DIR:-}" ]]; then
  export HOST_PROJECTS_DIR="${TMPDIR:-/tmp}/transcribe-docker-smoke-projects"
  mkdir -p "$HOST_PROJECTS_DIR"
fi

echo "Building transcribe-web image..."
docker compose -f docker-compose.yml build

echo "Compose bind honesty..."
bash "$ROOT_DIR/scripts/release/assert_compose_bind.sh"

if [[ "${TRANSCRIBE_SKIP_IMAGE_PIP_CHECK:-0}" != "1" ]]; then
  bash "$ROOT_DIR/scripts/release/image_pip_check.sh"
fi

echo "OK: Docker release smoke passed"
