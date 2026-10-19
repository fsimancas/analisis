import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fais.backup import create_backup


def test_online_backup_is_valid_and_retention_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE values_table(value TEXT)")
        conn.execute("INSERT INTO values_table VALUES ('preserved')")
    destination = tmp_path / "backups"
    start = datetime(2026, 10, 18, tzinfo=UTC)
    for offset in range(3):
        create_backup(source, destination, keep=2, now=start + timedelta(hours=offset))
    backups = sorted(destination.glob("*.sqlite3"))
    assert len(backups) == 2
    with sqlite3.connect(backups[-1]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT value FROM values_table").fetchone()[0] == "preserved"
