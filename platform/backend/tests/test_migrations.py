from pathlib import Path

from fais.db import Database
from fais.db.migrate import migrate


def test_migrations_are_idempotent_and_foreign_keys_are_valid(tmp_path: Path) -> None:
    database = Database(tmp_path / "canonical.sqlite3")
    assert migrate(database) == [
        "001_canonical.sql",
        "002_jobs_outbox.sql",
        "003_model_registry.sql",
        "004_temporal_precision.sql",
        "005_season_provenance.sql",
        "006_live_provider.sql",
        "007_identity.sql",
        "008_notifications.sql",
        "009_feed_files.sql",
        "010_notification_deliveries.sql",
        "011_administration.sql",
        "012_competition_permissions.sql",
        "013_detailed_match_entities.sql",
        "014_analyst_workspace.sql",
    ]
    assert migrate(database) == []
    with database.connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        versions = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert versions == 14
