#!/usr/bin/env bash
# pip check inside the freshly built production image.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${TRANSCRIBE_IMAGE:-transcribe:latest}"
OUT_DIR="${TRANSCRIBE_AUDIT_OUT:-$ROOT_DIR/artifacts/pre-release}"
mkdir -p "$OUT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: docker not available"
  exit 0
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "ERROR: image $IMAGE not found; build first"
  exit 1
fi

docker run --rm --entrypoint python "$IMAGE" -m pip check \
  | tee "$OUT_DIR/pip-check-image.txt"

docker run --rm --entrypoint python "$IMAGE" -m pip freeze \
  | tee "$OUT_DIR/pip-freeze-image.txt"

echo "OK: image pip check passed"
