#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${FAIS_PYTHON:-$PLATFORM_DIR/.venv/bin/python}"
RUFF_BIN="${FAIS_RUFF:-$PLATFORM_DIR/.venv/bin/ruff}"

cd "$PLATFORM_DIR/backend"
"$RUFF_BIN" check src tests
"$PYTHON_BIN" -m pytest

cd "$PLATFORM_DIR/web"
npm run lint
npm run build
npm run test:e2e

echo "FAIS verification completed"
