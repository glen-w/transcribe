#!/usr/bin/env bash
# transcribe.sh — create/activate a project-local venv and run CLI or UI.
# Keeps dependencies out of the system / other project interpreters.

set -euo pipefail

cd "$(dirname "$0")"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[Transcribe]${NC} $1"; }
print_success() { echo -e "${GREEN}[Transcribe]${NC} $1"; }
print_error() { echo -e "${RED}[Transcribe]${NC} $1"; }

resolve_python() {
  if [ -n "${TRANSCRIBE_PYTHON:-}" ]; then
    echo "$TRANSCRIBE_PYTHON"
    return
  fi
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done
  return 1
}

ensure_venv() {
  if [ -d ".venv" ]; then
    return
  fi
  local py
  if ! py="$(resolve_python)"; then
    print_error "Python 3.10+ is required but not found."
    exit 1
  fi
  print_status "Creating virtual environment with $py …"
  "$py" -m venv .venv
  print_status "Installing Transcribe (UI + core) into .venv …"
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -e '.[ui]'
  print_success "venv ready at .venv/"
}

ensure_venv
# shellcheck disable=SC1091
source .venv/bin/activate

cmd="${1:-ui}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$cmd" in
  ui | web)
    print_status "Starting Streamlit UI (port ${TRANSCRIBE_PORT:-8510}) …"
    exec transcribe-ui "$@"
    ;;
  install | setup)
    print_status "Refreshing editable install …"
    pip install -e '.[ui]'
    print_success "Installed."
    ;;
  install-dev)
    print_status "Installing with dev extras …"
    pip install -e '.[dev]'
    print_success "Installed (dev)."
    ;;
  cli | run)
    exec python -m transcribe "$@"
    ;;
  help | -h | --help)
    cat <<'EOF'
Usage: ./transcribe.sh [command] [args...]

Commands:
  ui | web          Start Streamlit UI (default)
  cli | run …       Run CLI: ./transcribe.sh cli models
  install | setup   Reinstall editable package with [ui]
  install-dev       Install editable package with [dev]
  help              Show this help

Environment:
  Copy .env.example → .env for TRANSCRIBE_* / HOST_* path overrides.
  TRANSCRIBE_PYTHON  Interpreter used to create .venv (optional)
EOF
    ;;
  *)
    # Treat unknown first token as CLI subcommand (e.g. ./transcribe.sh models)
    exec python -m transcribe "$cmd" "$@"
    ;;
esac
