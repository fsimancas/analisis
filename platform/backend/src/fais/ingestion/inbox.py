from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from fais.db import Database

from .json_feed import JsonMatchFeed


@dataclass(slots=True)
class InboxSummary:
    discovered: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    records_written: int = 0


class InboxScanner:
    """Import changed JSON files arranged as ``country/competition/*.json``."""

    def __init__(self, database: Database, root: str | Path):
        self.database = database
        self.root = Path(root).resolve()

    def scan(self) -> InboxSummary:
        summary = InboxSummary()
        if not self.root.exists():
            return summary
        for path in sorted(self.root.glob("*/*/*.json")):
            summary.discovered += 1
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = path.relative_to(self.root)
            with self.database.connect(readonly=True) as conn:
                previous = conn.execute(
                    "SELECT sha256, status FROM feed_files WHERE path=?", (str(relative),)
                ).fetchone()
            if previous and previous["sha256"] == digest and previous["status"] == "SUCCEEDED":
                summary.skipped += 1
                continue
            self._mark(relative, digest, "PROCESSING")
            captured_on = datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
            try:
                result = JsonMatchFeed(self.database).run(
                    path,
                    country_slug=relative.parts[0],
                    competition_slug=relative.parts[1],
                    captured_on=captured_on,
                )
            except Exception as error:
                self._mark(relative, digest, "FAILED", error=str(error)[:4000])
                summary.failed += 1
                continue
            values = asdict(result)
            written = values["inserted"] + values["updated"]
            self._mark(
                relative,
                digest,
                "SUCCEEDED",
                records_seen=values["seen"],
                records_written=written,
            )
            summary.processed += 1
            summary.records_written += written
        return summary

    def _mark(
        self,
        relative: Path,
        digest: str,
        status: str,
        *,
        records_seen: int = 0,
        records_written: int = 0,
        error: str | None = None,
    ) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO feed_files(
                    path, sha256, status, records_seen, records_written, error, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    sha256=excluded.sha256, status=excluded.status,
                    records_seen=excluded.records_seen,
                    records_written=excluded.records_written, error=excluded.error,
                    processed_at=CURRENT_TIMESTAMP
                """,
                (str(relative), digest, status, records_seen, records_written, error),
            )
