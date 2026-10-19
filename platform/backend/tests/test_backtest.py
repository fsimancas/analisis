from pathlib import Path

from fais.analytics import WalkForwardBacktest
from fais.db import Database
from fais.db.migrate import migrate


def seed_history(database: Database) -> None:
    with database.transaction() as conn:
        conn.execute("INSERT INTO countries(slug, name) VALUES ('test', 'Test')")
        country = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'league', 'League')",
            (country,),
        )
        competition = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        teams = []
        for name in ("Alpha", "Beta"):
            conn.execute(
                "INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?)",
                (name, name.lower(), country),
            )
            teams.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        for index in range(1, 13):
            conn.execute(
                """
                INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, kickoff_utc, kickoff_date,
                    kickoff_precision, status, match_type, home_score, away_score
                ) VALUES (?, ?, ?, ?, ?, 'MINUTE', 'FINISHED', 'RESULT', ?, ?)
                """,
                (
                    competition,
                    teams[index % 2],
                    teams[(index + 1) % 2],
                    f"2026-01-{index:02d}T12:00:00Z",
                    f"2026-01-{index:02d}",
                    index % 4,
                    (index + 1) % 3,
                ),
            )


def test_walk_forward_backtest_persists_bounded_metrics(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    migrate(database)
    seed_history(database)
    result = WalkForwardBacktest(database).run(min_team_history=2)
    assert result["evaluated"] == 10
    assert result["log_loss"] > 0
    assert 0 <= result["accuracy"] <= 1
    assert 0 <= result["expected_calibration_error"] <= 1
    with database.connect(readonly=True) as conn:
        row = conn.execute("SELECT status, metrics FROM backtest_runs").fetchone()
        assert row["status"] == "SUCCEEDED"
        assert row["metrics"] is not None
