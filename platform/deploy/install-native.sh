#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on the target system." >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 sports.example.com" >&2
  exit 2
fi

DOMAIN="$1"
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_SOURCE="$(cd -- "$DEPLOY_DIR/.." && pwd)"
INSTALL_ROOT="/opt/fais/platform"
RUNTIME_ROOT="/opt/fais/runtime"

id fais >/dev/null 2>&1 || useradd --system --home /var/lib/fais --shell /usr/sbin/nologin fais
install -d -o fais -g fais -m 0750 /var/lib/fais /var/lib/fais/inbox /var/lib/fais/redis
install -d -o fais -g fais -m 0750 /var/lib/fais/caddy /var/backups/fais
install -d -o root -g fais -m 0750 /etc/fais
install -d -o root -g root -m 0755 "$INSTALL_ROOT"
install -d -o fais -g fais -m 0755 "$RUNTIME_ROOT"

rsync -a --delete \
  --exclude '.runtime/' --exclude '.venv/' --exclude 'data/' \
  --exclude 'web/node_modules/' --exclude 'web/test-results/' \
  "$PLATFORM_SOURCE/" "$INSTALL_ROOT/"

if [[ ! -x "$RUNTIME_ROOT/caddy/caddy" || ! -x "$RUNTIME_ROOT/redis/bin/redis-server" ]]; then
  runuser -u fais -- "$INSTALL_ROOT/scripts/build_native_runtime.sh" "$RUNTIME_ROOT"
fi

python3 -m venv "$INSTALL_ROOT/.venv"
"$INSTALL_ROOT/.venv/bin/pip" install --upgrade pip
"$INSTALL_ROOT/.venv/bin/pip" install "$INSTALL_ROOT/backend[ml]"
npm --prefix "$INSTALL_ROOT/web" ci
npm --prefix "$INSTALL_ROOT/web" run build

if [[ ! -f /etc/fais/fais.env ]]; then
  "$INSTALL_ROOT/.venv/bin/python" "$INSTALL_ROOT/scripts/generate_env.py" \
    /etc/fais/fais.env --domain "$DOMAIN"
fi
install -o root -g fais -m 0640 "$DEPLOY_DIR/Caddyfile" /etc/fais/Caddyfile
install -o root -g fais -m 0640 "$DEPLOY_DIR/redis.conf" /etc/fais/redis.conf
install -o root -g root -m 0644 "$DEPLOY_DIR"/systemd/* /etc/systemd/system/
chown -R fais:fais /var/lib/fais /var/backups/fais "$RUNTIME_ROOT"

set -a
# shellcheck disable=SC1091
source /etc/fais/fais.env
set +a
"$INSTALL_ROOT/.venv/bin/fais" check-config
"$INSTALL_ROOT/.venv/bin/fais" migrate
FAIS_DOMAIN="$DOMAIN" XDG_DATA_HOME=/var/lib/fais/caddy \
  "$RUNTIME_ROOT/caddy/caddy" validate --config /etc/fais/Caddyfile --adapter caddyfile

systemctl daemon-reload
systemctl enable --now fais-redis fais-api fais-worker fais-beat fais-caddy fais-backup.timer
systemctl --no-pager --full status fais-api fais-worker fais-caddy

echo "Native deployment completed for https://$DOMAIN"
