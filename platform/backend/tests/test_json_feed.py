import json
from datetime import date
from pathlib import Path

from fais.db import Database
from fais.db.migrate import migrate
from fais.ingestion.json_feed import JsonMatchFeed


def seed_catalog(database: Database) -> None:
    with database.transaction() as conn:
        conn.execute("INSERT INTO countries(slug, name) VALUES ('colombia', 'Colombia')")
        country_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO competitions(country_id, slug, name)
            VALUES (?, 'primera-a', 'Primera A')
            """,
            (country_id,),
        )


def write_feed(path: Path, *, finished: bool) -> None:
    record = {
        "id": "live-1",
        "tipo": "resultado" if finished else "proximo",
        "estado": "finalizado" if finished else "por_jugar",
        "jornada": "Jornada 1",
        "fecha_hora": "18.10. 14:30",
        "equipo_local": "Equipo A",
        "equipo_visitante": "Equipo B",
        "goles_local": 2 if finished else None,
        "goles_visitante": 1 if finished else None,
        "link": "https://example.test/live-1",
    }
    path.write_text(json.dumps([record]), encoding="utf-8")


def test_json_feed_updates_existing_match_instead_of_duplicating(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    seed_catalog(database)
    feed_path = tmp_path / "feed.json"
    write_feed(feed_path, finished=False)
    importer = JsonMatchFeed(database)
    first = importer.run(
        feed_path,
        country_slug="colombia",
        competition_slug="primera-a",
        captured_on=date(2026, 10, 18),
    )
    write_feed(feed_path, finished=True)
    second = importer.run(
        feed_path,
        country_slug="colombia",
        competition_slug="primera-a",
        captured_on=date(2026, 10, 18),
    )
    assert first.inserted == 1
    assert second.updated == 1
    with database.connect(readonly=True) as conn:
        row = conn.execute("SELECT status, home_score, kickoff_utc FROM matches").fetchone()
        assert tuple(row) == ("FINISHED", 2, "2026-10-18T19:30:00Z")
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM ingestion_runs").fetchone()[0] == 2
