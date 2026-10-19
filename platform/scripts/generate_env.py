#!/usr/bin/env python3
"""Create a restrictive production environment file without printing its secret."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--database", type=Path, default=Path("/var/lib/fais/fais.sqlite3"))
    parser.add_argument("--inbox", type=Path, default=Path("/var/lib/fais/inbox"))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {args.output}")
    if any(char.isspace() for char in args.domain) or "/" in args.domain:
        raise SystemExit("Domain must be a bare hostname")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        (
            "FAIS_ENVIRONMENT=production",
            f"FAIS_DATABASE_PATH={args.database.resolve()}",
            f"FAIS_INBOX_PATH={args.inbox.resolve()}",
            "FAIS_REDIS_URL=redis://127.0.0.1:6379/0",
            f"FAIS_CORS_ORIGINS=https://{args.domain}",
            "FAIS_LOG_LEVEL=INFO",
            f"FAIS_AUTH_SECRET={secrets.token_urlsafe(48)}",
            "FAIS_ACCESS_TOKEN_MINUTES=480",
            "",
        )
    )
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(content)
    print(f"Created {args.output} with mode 0600")


if __name__ == "__main__":
    main()
