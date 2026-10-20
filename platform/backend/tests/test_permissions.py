from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.auth import AuthService
from fais.config import Settings


def test_competition_permissions_and_role_guards(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "permissions.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.database.transaction() as conn:
            conn.execute("INSERT INTO countries(slug, name) VALUES ('co', 'Colombia')")
            country_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            competition_ids = []
            match_ids = []
            for index in range(2):
                conn.execute(
                    "INSERT INTO competitions(country_id, slug, name) VALUES (?, ?, ?)",
                    (country_id, f"league-{index}", f"League {index}"),
                )
                competition_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                competition_ids.append(competition_id)
                team_ids = []
                for side in ("home", "away"):
                    name = f"{side}-{index}"
                    conn.execute(
                        """INSERT INTO teams(canonical_name, normalized_name, country_id)
                        VALUES (?, ?, ?)""",
                        (name, name, country_id),
                    )
                    team_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                conn.execute(
                    """INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, status, match_type
                    ) VALUES (?, ?, ?, 'SCHEDULED', 'UPCOMING')""",
                    (competition_id, *team_ids),
                )
                match_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "scoped@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Scoped user",
            },
        ).json()
        service = AuthService(app.state.database, settings)
        admin = service.bootstrap_admin(
            "admin@example.com", "secure-admin-password", "Administrator"
        )
        analyst = client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Analyst",
            },
        ).json()["user"]
        with app.state.database.transaction() as conn:
            conn.execute("UPDATE users SET role='ANALYST' WHERE id=?", (analyst["id"],))
        user_headers = {"Authorization": f"Bearer {registered['access_token']}"}
        admin_headers = {"Authorization": f"Bearer {service.token(admin)}"}
        analyst_headers = {
            "Authorization": f"Bearer {service.token({**analyst, 'role': 'ANALYST'})}"
        }

        denied = client.get("/api/v1/quality/issues", headers=user_headers)
        assert denied.status_code == 403
        empty = client.get("/api/v1/matches", headers=user_headers)
        assert empty.json() == []
        assignment = client.put(
            f"/api/v1/admin/users/{registered['user']['id']}/competition-permissions",
            json={"competition_ids": [competition_ids[0]]},
            headers=admin_headers,
        )
        assert assignment.status_code == 200

        visible = client.get("/api/v1/matches", headers=user_headers)
        assert [item["id"] for item in visible.json()] == [match_ids[0]]
        assert (
            client.get(f"/api/v1/matches/{match_ids[1]}", headers=user_headers).status_code == 404
        )
        assert len(client.get("/api/v1/matches", headers=analyst_headers).json()) == 2
        assert client.get("/api/v1/quality/issues", headers=analyst_headers).status_code == 200
        forbidden_favorite = client.post(
            "/api/v1/favorites", json={"match_id": match_ids[1]}, headers=user_headers
        )
        assert forbidden_favorite.status_code == 404

        graphql = client.post(
            "/graphql",
            json={"query": "{ competitions { id name } matches { id } }"},
            headers=user_headers,
        )
        assert graphql.status_code == 200
        assert [item["id"] for item in graphql.json()["data"]["competitions"]] == [
            competition_ids[0]
        ]
        assert [item["id"] for item in graphql.json()["data"]["matches"]] == [match_ids[0]]
