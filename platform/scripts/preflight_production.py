#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import ssl

from fais.config import Settings
from fais.db import Database
from redis import Redis
from redis.exceptions import RedisError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-tls", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    checks: dict[str, object] = {"configuration": settings.deployment_issues()}
    database = Database(settings.database_path)
    try:
        with database.connect(readonly=True) as conn:
            checks["database"] = conn.execute("PRAGMA quick_check").fetchone()[0]
    except (sqlite3.Error, OSError) as error:
        checks["database"] = f"error: {error}"
    try:
        redis = Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
        checks["redis"] = "ok" if redis.ping() else "error"
        redis.close()
    except (RedisError, OSError) as error:
        checks["redis"] = f"error: {error}"
    if settings.public_domain:
        try:
            addresses = sorted(
                {item[4][0] for item in socket.getaddrinfo(settings.public_domain, 443)}
            )
            checks["dns"] = addresses
        except OSError as error:
            checks["dns"] = f"error: {error}"
        if args.require_tls:
            try:
                context = ssl.create_default_context()
                with (
                    socket.create_connection((settings.public_domain, 443), timeout=5) as raw,
                    context.wrap_socket(raw, server_hostname=settings.public_domain) as tls,
                ):
                    certificate = tls.getpeercert()
                checks["tls"] = certificate.get("notAfter", "ok")
            except (OSError, ssl.SSLError) as error:
                checks["tls"] = f"error: {error}"
    failed = bool(checks["configuration"]) or any(
        isinstance(value, str) and value != "ok" and value.startswith("error:")
        for key, value in checks.items()
        if key != "configuration"
    )
    print(json.dumps({"ready": not failed, "checks": checks}, indent=2))
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
