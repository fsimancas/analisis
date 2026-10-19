from __future__ import annotations

import json
from pathlib import Path

from fais.db import Database
from fais.db.migrate import migrate
from fais.ingestion.inbox import InboxScanner


def _seed(database: Database) -> None:
    with database.transaction() as conn:
        conn.execute("INSERT INTO countries(slug, name) VALUES ('colombia', 'Colombia')")
        country_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'primera-a', 'A')",
            (country_id,),
        )


def _record(score: int | None = None) -> list[dict]:
    return [
        {
            "id": "inbox-1",
            "tipo": "resultado" if score is not None else "proximo",
            "estado": "finalizado" if score is not None else "por_jugar",
            "fecha_hora": "18.10. 14:30",
            "equipo_local": "Local",
            "equipo_visitante": "Visitante",
            "goles_local": score,
            "goles_visitante": 0 if score is not None else None,
        }
    ]


def test_inbox_is_idempotent_and_reprocesses_changed_files(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    _seed(database)
    feed = tmp_path / "inbox/colombia/primera-a/feed.json"
    feed.parent.mkdir(parents=True)
    feed.write_text(json.dumps(_record()), encoding="utf-8")
    scanner = InboxScanner(database, tmp_path / "inbox")

    first = scanner.scan()
    unchanged = scanner.scan()
    feed.write_text(json.dumps(_record(2)), encoding="utf-8")
    changed = scanner.scan()

    assert (first.processed, unchanged.skipped, changed.processed) == (1, 1, 1)
    with database.connect(readonly=True) as conn:
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 1
        assert conn.execute("SELECT home_score FROM matches").fetchone()[0] == 2


def test_inbox_records_failure_without_blocking_other_files(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    _seed(database)
    good = tmp_path / "inbox/colombia/primera-a/good.json"
    good.parent.mkdir(parents=True)
    good.write_text(json.dumps(_record()), encoding="utf-8")
    bad = tmp_path / "inbox/colombia/primera-a/bad.json"
    bad.write_text("not-json", encoding="utf-8")

    result = InboxScanner(database, tmp_path / "inbox").scan()

    assert (result.processed, result.failed) == (1, 1)
    with database.connect(readonly=True) as conn:
        status = conn.execute(
            "SELECT status FROM feed_files WHERE path LIKE '%bad.json'"
        ).fetchone()[0]
        assert status == "FAILED"
