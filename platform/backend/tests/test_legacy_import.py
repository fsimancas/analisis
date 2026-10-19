import sqlite3
from pathlib import Path

from fais.db import Database
from fais.db.migrate import migrate
from fais.ingestion import LegacyImporter


def build_legacy(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE paises (
          id INTEGER PRIMARY KEY, nombre_betplay TEXT, nombre_flashscore TEXT,
          slug TEXT, link_flashscore TEXT, total_competiciones INTEGER
        );
        CREATE TABLE competiciones (
          id INTEGER PRIMARY KEY, pais_id INTEGER, pais_nombre TEXT,
          nombre_betplay TEXT, nombre_flashscore TEXT, link_flashscore TEXT
        );
        CREATE TABLE partidos (
          id TEXT PRIMARY KEY, competicion_id INTEGER, tipo TEXT, jornada TEXT,
          fecha_hora TEXT, equipo_local TEXT, equipo_visitante TEXT,
          goles_local INTEGER, goles_visitante INTEGER, link TEXT, estado TEXT
        );
        INSERT INTO paises
        VALUES (1, 'Colombia', 'Colombia', 'colombia', 'https://example.test', 1);
        INSERT INTO competiciones VALUES (10, 1, 'Colombia', 'Primera A', 'Primera A', 'https://example.test/a');
        INSERT INTO partidos VALUES (
          'legacy-1', 10, 'resultado', 'Jornada 1', '2026-10-01T20:00:00Z',
          'Equipo A', 'Equipo B', 2, 1, 'https://example.test/m', 'finalizado'
        );
        """
    )
    conn.commit()
    conn.close()


def test_import_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite3"
    build_legacy(legacy)
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    importer = LegacyImporter(database)
    first = importer.run(legacy)
    second = importer.run(legacy)
    assert first.matches == second.matches == 1
    with database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM match_provider_refs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM teams").fetchone()[0] == 2
        assert (
            conn.execute("SELECT kickoff_utc FROM matches").fetchone()[0] == "2026-10-01T20:00:00Z"
        )
