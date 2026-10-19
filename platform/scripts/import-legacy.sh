#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 /ruta/al/betplay_flashscore_lite.db" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${FAIS_VENV_PATH:-$PLATFORM_DIR/.venv}"
export FAIS_DATABASE_PATH="${FAIS_DATABASE_PATH:-$PLATFORM_DIR/data/fais.sqlite3}"

exec "$VENV_DIR/bin/fais" import-legacy "$1"
