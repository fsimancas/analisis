from __future__ import annotations

import json
from pathlib import Path

from fais.auth import AuthService
from fais.config import Settings
from fais.db import Database
from fais.db.migrate import migrate
from fais.notification_delivery import DeliverySummary, dispatch_webhook_notifications
from fais.notifications import create_notifications


class RecordingNotifier:
    def __init__(self, *, fails: bool = False):
        self.fails = fails
        self.payloads: list[dict] = []

    def send(self, payload: dict) -> None:
        self.payloads.append(payload)
        if self.fails:
            raise RuntimeError("provider unavailable")


def _notification(database: Database) -> None:
    settings = Settings(database.path, "redis://localhost", (), "INFO", auth_secret="test")
    user = AuthService(database, settings).register("user@example.com", "long-password", "User")
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
                "INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?)",
                (name, name.lower(), country),
            )
        teams = [row[0] for row in conn.execute("SELECT id FROM teams ORDER BY id")]
        conn.execute(
            """
            INSERT INTO matches(competition_id, home_team_id, away_team_id, status, match_type)
            VALUES (?, ?, ?, 'SCHEDULED', 'UPCOMING')
            """,
            (competition, teams[0], teams[1]),
        )
        match_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO alerts(user_id, match_id, event_type) VALUES (?, ?, 'KICKOFF')",
            (user["id"], match_id),
        )
    assert create_notifications(database, "match.kickoff", "event-1", {"match_id": match_id})


def test_webhook_delivery_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "notifications.sqlite3")
    migrate(database)
    _notification(database)
    notifier = RecordingNotifier()

    first = dispatch_webhook_notifications(database, notifier)
    second = dispatch_webhook_notifications(database, notifier)

    assert first == DeliverySummary(delivered=1)
    assert second == DeliverySummary()
    assert notifier.payloads[0]["recipient"] == "user@example.com"
    assert json.dumps(notifier.payloads[0]["payload"])


def test_failed_webhook_is_scheduled_for_retry(tmp_path: Path) -> None:
    database = Database(tmp_path / "notifications.sqlite3")
    migrate(database)
    _notification(database)

    result = dispatch_webhook_notifications(database, RecordingNotifier(fails=True))

    assert result == DeliverySummary(failed=1)
    with database.connect(readonly=True) as conn:
        row = conn.execute(
            "SELECT status, attempts, next_attempt_at FROM notification_deliveries"
        ).fetchone()
        assert tuple(row) == ("FAILED", 1, row["next_attempt_at"])
        assert row["next_attempt_at"] is not None
