from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def create_backup(
    database: str | Path,
    destination: str | Path,
    *,
    keep: int = 14,
    now: datetime | None = None,
) -> Path:
    source_path = Path(database).resolve()
    destination_path = Path(destination).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {source_path}")
    destination_path.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = destination_path / f"fais-{stamp}.sqlite3"
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result}")
    finally:
        target.close()
        source.close()
    backups = sorted(destination_path.glob("fais-*.sqlite3"), reverse=True)
    for expired in backups[max(keep, 1) :]:
        expired.unlink()
    return backup_path
