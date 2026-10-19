from pathlib import Path

from fais.analytics import PredictionEngine
from fais.db import Database
from fais.db.migrate import migrate


def seed(database: Database) -> tuple[int, int]:
    with database.transaction() as conn:
        conn.execute("INSERT INTO countries(slug, name) VALUES ('test', 'Test')")
        country_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'league', 'League')",
            (country_id,),
        )
        competition_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        team_ids = []
        for name in ("Alpha", "Beta", "Gamma", "Delta"):
            conn.execute(
                "INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?)",
                (name, name.lower(), country_id),
            )
            team_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        def match(home, away, kickoff, hs, as_, status="FINISHED"):
            conn.execute(
                """
                INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, kickoff_utc,
                    status, match_type, home_score, away_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    competition_id,
                    home,
                    away,
                    kickoff,
                    status,
                    "RESULT" if status == "FINISHED" else "UPCOMING",
                    hs,
                    as_,
                ),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        match(team_ids[0], team_ids[2], "2026-01-01T12:00:00Z", 2, 0)
        match(team_ids[3], team_ids[1], "2026-01-08T12:00:00Z", 1, 1)
        target = match(team_ids[0], team_ids[1], "2026-02-01T12:00:00Z", None, None, "SCHEDULED")
        future = match(team_ids[0], team_ids[1], "2026-03-01T12:00:00Z", 8, 8)
    return target, future


def test_prediction_probabilities_and_temporal_isolation(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    target, future = seed(database)
    engine = PredictionEngine(database)
    before = engine.predict(target)
    with database.transaction() as conn:
        conn.execute("UPDATE matches SET home_score=0, away_score=9 WHERE id=?", (future,))
    after = engine.predict(target)
    assert before == after
    probabilities = before["markets"]["one_x_two"]
    assert abs(sum(probabilities.values()) - 1.0) < 1e-9
    assert abs(sum(sum(row) for row in before["score_matrix"]) - 1.0) < 1e-9


def test_prediction_rejects_ambiguous_cutoff(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    target, _ = seed(database)
    with database.transaction() as conn:
        conn.execute(
            "UPDATE matches SET kickoff_utc=NULL, kickoff_raw='20.10. 18:00' WHERE id=?", (target,)
        )
    try:
        PredictionEngine(database).predict(target)
    except ValueError as exc:
        assert "temporal features are blocked" in str(exc)
    else:
        raise AssertionError("Ambiguous cutoff must block prediction")
