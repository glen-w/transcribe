#!/usr/bin/env bash
# Canonical Compose bind assertions. Uses ONLY docker-compose.yml (no local override).
# Static file check always runs. Live `docker compose config` runs when Docker is available.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
fail=0

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: docker-compose.yml missing"
  exit 1
fi

# Default published mapping must stay loopback unless TRANSCRIBE_BIND_HOST is set.
if ! grep -qE '\$\{TRANSCRIBE_BIND_HOST:-127\.0\.0\.1\}:8510:8510' "$COMPOSE_FILE"; then
  echo "ERROR: docker-compose.yml default publish is not 127.0.0.1:8510:8510"
  echo "  expected: \"\${TRANSCRIBE_BIND_HOST:-127.0.0.1}:8510:8510\""
  fail=1
else
  echo "OK: static default bind is loopback 127.0.0.1:8510"
fi

if grep -E '^\s+-\s+"?0\.0\.0\.0:8510:8510' "$COMPOSE_FILE" >/dev/null; then
  echo "ERROR: docker-compose.yml hard-codes LAN bind 0.0.0.0:8510"
  fail=1
fi

if ! command -v docker >/dev/null 2>&1; then
  if [[ "${TRANSCRIBE_STRICT_COMPOSE:-0}" == "1" ]]; then
    echo "ERROR: docker not available (TRANSCRIBE_STRICT_COMPOSE=1)"
    exit 1
  fi
  echo "SKIP: docker not available; live compose-config not run"
  if [[ "$fail" -ne 0 ]]; then
    exit 1
  fi
  echo "OK: canonical compose bind assertions passed (static)"
  exit 0
fi

COMPOSE_BIN=(docker compose -f docker-compose.yml)

# docker-compose.yml requires HOST_PROJECTS_DIR for volume interpolation.
if [[ -z "${HOST_PROJECTS_DIR:-}" ]]; then
  export HOST_PROJECTS_DIR="${TMPDIR:-/tmp}/transcribe-compose-assert-projects"
  mkdir -p "$HOST_PROJECTS_DIR"
fi

_extract_published_ports() {
  local json="$1"
  python3 - "$json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
svc = data.get("services", {}).get("transcribe-web", {})
ports = svc.get("ports") or []
out = []
for p in ports:
    if isinstance(p, dict):
        published = p.get("published")
        target = p.get("target")
        host_ip = p.get("host_ip") or ""
        if published is None or target is None:
            continue
        out.append(f"{host_ip}:{published}:{target}" if host_ip else f"{published}:{target}")
    else:
        out.append(str(p))
for line in sorted(out):
    print(line)
PY
}

_assert_ports() {
  local label="$1"
  shift
  local expected=("$@")
  local json
  json="$("${COMPOSE_BIN[@]}" config --format json)"
  local actual
  actual="$(_extract_published_ports "$json")"
  local -a actual_arr=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && actual_arr+=("$line")
  done <<< "$actual"

  if [[ ${#actual_arr[@]} -ne ${#expected[@]} ]]; then
    echo "ERROR [$label]: expected ${#expected[@]} published port(s), got ${#actual_arr[@]}"
    echo "  expected: ${expected[*]}"
    echo "  actual:   ${actual_arr[*]:-<none>}"
    exit 1
  fi
  local i
  for i in "${!expected[@]}"; do
    if [[ "${actual_arr[$i]}" != "${expected[$i]}" ]]; then
      echo "ERROR [$label]: port mismatch at index $i"
      echo "  expected: ${expected[$i]}"
      echo "  actual:   ${actual_arr[$i]}"
      echo "  all actual: ${actual_arr[*]}"
      exit 1
    fi
  done
  echo "OK [$label]: ${actual_arr[*]}"
}

unset TRANSCRIBE_BIND_HOST || true
_assert_ports "default loopback" "127.0.0.1:8510:8510"

export TRANSCRIBE_BIND_HOST=0.0.0.0
_assert_ports "lan opt-in" "0.0.0.0:8510:8510"
unset TRANSCRIBE_BIND_HOST || true

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "OK: canonical compose bind assertions passed"
