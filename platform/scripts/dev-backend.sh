#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PLATFORM_DIR/backend"
VENV_DIR="${FAIS_VENV_PATH:-$PLATFORM_DIR/.venv}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -e "$BACKEND_DIR[dev]"
fi

export FAIS_DATABASE_PATH="${FAIS_DATABASE_PATH:-$PLATFORM_DIR/data/fais.sqlite3}"
exec "$VENV_DIR/bin/uvicorn" fais.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000
