from pathlib import Path

from fais.auth import AuthService
from fais.config import Settings
from fais.db import Database
from fais.db.migrate import migrate
from fais.notifications import create_notifications


def test_prediction_event_creates_one_idempotent_user_notification(tmp_path: Path) -> None:
    database = Database(tmp_path / "notifications.sqlite3")
    migrate(database)
    settings = Settings(
        database_path=database.path,
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=(),
        log_level="INFO",
        auth_secret="test-secret",
    )
    user = AuthService(database, settings).register(
        "user@example.com", "long-enough-password", "User"
    )
    with database.transaction() as conn:
        conn.execute("INSERT INTO countries(slug, name) VALUES ('test', 'Test')")
        country = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'league', 'League')",
            (country,),
        )
        competition = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for name in ("A", "B"):
            conn.execute(
                """
                INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?)
                """,
                (name, name.lower(), country),
            )
        teams = [row[0] for row in conn.execute("SELECT id FROM teams")]
        conn.execute(
            """
            INSERT INTO matches(competition_id, home_team_id, away_team_id, status, match_type)
            VALUES (?, ?, ?, 'SCHEDULED', 'UPCOMING')
            """,
            (competition, teams[0], teams[1]),
        )
        match_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO alerts(user_id, match_id, event_type)
            VALUES (?, ?, 'PREDICTION_READY')
            """,
            (user["id"], match_id),
        )
    payload = {"match_id": match_id, "result": {"home": 0.5}}
    assert create_notifications(database, "prediction.completed", "job-1", payload) == 1
    assert create_notifications(database, "prediction.completed", "job-1", payload) == 0
    with database.connect(readonly=True) as conn:
        assert conn.execute("SELECT count(*) FROM notifications").fetchone()[0] == 1
