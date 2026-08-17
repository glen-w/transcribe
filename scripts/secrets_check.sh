#!/bin/bash
# Secrets + path denylist gate. Consumes scripts/release/path_denylist.toml via check_denylist.py.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

fail=0

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    python3 "$ROOT_DIR/scripts/release/check_denylist.py" || fail=1
else
    echo "INFO: Not a git repository; skipping tracked-file checks."
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi

echo "OK: secrets_check + denylist passed."
