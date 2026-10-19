import sqlite3

from fais.ingestion.seasons import assign_dataset_seasons, season_from_range


def test_season_labels_preserve_calendar_and_cross_year_cycles() -> None:
    assert season_from_range("2026-01-20", "2026-12-02").name == "2026"
    assert season_from_range("2026-08-20", "2027-05-30").name == "2026/27"
    cycle = season_from_range("2023-09-07", "2026-07-19")
    assert cycle.name == "2023-2026"
    assert cycle.confidence < 0.9


def test_dataset_season_assignment_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE seasons (
          id INTEGER PRIMARY KEY, competition_id INTEGER, name TEXT, starts_at TEXT,
          ends_at TEXT, assignment_method TEXT, confidence REAL,
          UNIQUE(competition_id, name)
        );
        CREATE TABLE matches (
          id INTEGER PRIMARY KEY, competition_id INTEGER, kickoff_date TEXT, season_id INTEGER
        );
        INSERT INTO matches(competition_id, kickoff_date)
        VALUES (1, '2026-08-20'), (1, '2027-05-30');
        """
    )
    assert assign_dataset_seasons(conn) == 1
    assert assign_dataset_seasons(conn) == 1
    assert conn.execute("SELECT count(*) FROM seasons").fetchone()[0] == 1
    assert (
        conn.execute("SELECT count(*) FROM matches WHERE season_id IS NOT NULL").fetchone()[0] == 2
    )
