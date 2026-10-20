from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.config import Settings


def test_identity_favorites_and_alerts_are_user_scoped(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "identity.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.database.transaction() as conn:
            conn.execute("INSERT INTO countries(slug, name) VALUES ('test', 'Test')")
            country = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'league', 'League')",
                (country,),
            )
            competition = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for name in ("Alpha", "Beta"):
                conn.execute(
                    """
                    INSERT INTO teams(canonical_name, normalized_name, country_id)
                    VALUES (?, ?, ?)
                    """,
                    (name, name.lower(), country),
                )
            teams = [row[0] for row in conn.execute("SELECT id FROM teams ORDER BY id")]
            conn.execute(
                """
                INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, status, match_type
                ) VALUES (?, ?, ?, 'SCHEDULED', 'UPCOMING')
                """,
                (competition, teams[0], teams[1]),
            )
            match_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Analyst",
            },
        )
        assert registration.status_code == 201
        token = registration.json()["access_token"]
        with app.state.database.transaction() as conn:
            user_id = conn.execute(
                "SELECT id FROM users WHERE email='analyst@example.com'"
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO user_competition_permissions(user_id, competition_id)
                VALUES (?, ?)""",
                (user_id, competition),
            )
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        favorite = client.post("/api/v1/favorites", json={"team_id": teams[0]}, headers=headers)
        assert favorite.status_code == 201
        alert = client.post(
            "/api/v1/alerts",
            json={"match_id": match_id, "event_type": "KICKOFF"},
            headers=headers,
        )
        assert alert.status_code == 201
        assert len(client.get("/api/v1/favorites", headers=headers).json()) == 1
        assert len(client.get("/api/v1/alerts", headers=headers).json()) == 1
        assert client.get("/api/v1/auth/me").status_code == 401
