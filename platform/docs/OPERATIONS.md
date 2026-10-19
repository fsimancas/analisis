# Operación nativa

## Servicios

La instalación de producción usa paquetes del sistema y `systemd`, sin
contenedores. Se necesitan Python 3.12, Node.js para compilar, Redis, Caddy y un
usuario de sistema `fais`. El artefacto web compilado no necesita Node en
ejecución.

1. Instalar el backend en `/opt/fais/platform/.venv`.
2. Ejecutar `npm ci && npm run build` en `web/`.
3. Crear `/var/lib/fais`, `/var/backups/fais` y `/etc/fais` para el usuario `fais`.
4. Copiar `deploy/fais.env.example` a `/etc/fais/fais.env` y cambiar el secreto.
5. Instalar las unidades de `deploy/systemd/` y el `deploy/Caddyfile`.
6. Activar `fais-api`, `fais-worker`, `fais-beat`, `fais-backup.timer`, Redis y Caddy.

La instalación completa puede ejecutarse en un servidor Debian/Ubuntu limpio,
sin contenedores, con:

```bash
sudo ./deploy/install-native.sh sports.example.com
```

El instalador compila Redis de forma nativa, instala Caddy, crea el usuario
restringido `fais`, genera el secreto, compila React, valida la configuración y
activa todos los servicios. No modifica un `/etc/fais/fais.env` ya existente.

Generar el entorno sin mostrar el secreto en la terminal:

```bash
python scripts/generate_env.py /etc/fais/fais.env --domain sports.example.com
FAIS_ADMIN_PASSWORD='use-a-secret-manager' .venv/bin/fais bootstrap-admin \
  --email admin@example.com
.venv/bin/fais check-config
```

La variable de contraseña es solo para automatización; en una terminal se
recomienda omitirla y usar el prompt oculto.

El worker debe conservar `--concurrency=1`: es el escritor serial de SQLite.
Las réplicas FastAPI son lectoras salvo personalización de bajo volumen.

## Salud y métricas

- `/api/v1/health`: vida del proceso.
- `/api/v1/readiness`: SQLite, Redis y eventos pendientes.
- `/metrics`: contadores Prometheus en texto abierto.

Los ejemplos de scrape y alertas están en `deploy/prometheus/`. Prometheus
consulta el puerto local 8000; Caddy no publica `/metrics` a Internet.

## Backup y restauración

`backup_sqlite.py` usa la API de backup online, valida `integrity_check` y rota
copias. Para restaurar, detener API/workers, verificar la copia nuevamente,
copiarla a una ruta nueva y cambiar `FAIS_DATABASE_PATH`; no sobrescribir la base
activa hasta validar REST, GraphQL y conteos.

## Comprobación previa a publicación

```bash
./scripts/verify.sh
curl http://127.0.0.1:8000/api/v1/readiness
curl http://127.0.0.1:8000/metrics
set -a; source /etc/fais/fais.env; set +a
.venv/bin/python scripts/preflight_production.py --require-tls
```

La exposición pública requiere HTTPS, un secreto aleatorio de al menos 32 bytes
y restricción de `/metrics` por IP en Caddy. Para SSO corporativo se sustituye
el login local por OIDC sin cambiar las tablas de favoritos o alertas.
