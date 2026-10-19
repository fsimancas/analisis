#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PREFIX="${1:-$PLATFORM_DIR/.runtime}"
REDIS_VERSION="8.8.3"
CADDY_VERSION="2.11.7"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf -- "$BUILD_DIR"' EXIT

if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "The pinned Caddy binary currently supports x86_64 only." >&2
  exit 2
fi

mkdir -p "$PREFIX/caddy" "$PREFIX/redis"

curl --fail --location \
  "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
  --output "$BUILD_DIR/caddy.tar.gz"
tar -xzf "$BUILD_DIR/caddy.tar.gz" -C "$PREFIX/caddy" caddy
chmod 0755 "$PREFIX/caddy/caddy"

git clone --depth 1 --branch "$REDIS_VERSION" https://github.com/redis/redis.git "$BUILD_DIR/redis"
make -C "$BUILD_DIR/redis" -j"$(getconf _NPROCESSORS_ONLN)" BUILD_TLS=no
make -C "$BUILD_DIR/redis" install PREFIX="$PREFIX/redis"

"$PREFIX/caddy/caddy" version
"$PREFIX/redis/bin/redis-server" --version
