#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd -- "$SCRIPT_DIR/../web" && pwd)"

cd "$WEB_DIR"
if [[ ! -d node_modules ]]; then
  npm ci --cache "${FAIS_NPM_CACHE:-/tmp/fais-npm-cache}"
fi
exec npm run dev -- --host 127.0.0.1
