from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.auth import AuthService
from fais.config import Settings


def _app(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "admin-management.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    return create_app(settings), settings


def _headers(token: str, *, confirm: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if confirm:
        headers["X-Confirm-Action"] = "delete"
    return headers


def test_admin_crud_quality_users_merging_and_audit(tmp_path: Path) -> None:
    app, settings = _app(tmp_path)
    with TestClient(app) as client:
        service = AuthService(app.state.database, settings)
        admin = service.bootstrap_admin("admin@example.com", "secure-admin-password", "Admin")
        user = service.register("user@example.com", "secure-user-password", "User")
        admin_headers = _headers(service.token(admin))
        user_headers = _headers(service.token(user))
        assert client.get("/api/v1/admin/summary", headers=user_headers).status_code == 403

        country = client.post(
            "/api/v1/admin/countries",
            headers=admin_headers,
            json={"slug": "colombia", "name": "Colombia"},
        ).json()
        competition = client.post(
            "/api/v1/admin/competitions",
            headers=admin_headers,
            json={
                "country_id": country["id"],
                "slug": "primera-a",
                "name": "Primera A",
                "sport": "football",
                "active": True,
            },
        ).json()
        teams = [
            client.post(
                "/api/v1/admin/teams",
                headers=admin_headers,
                json={"country_id": country["id"], "canonical_name": name},
            ).json()
            for name in ("Alpha", "Beta", "Alpha FC")
        ]
        alias = client.post(
            f"/api/v1/admin/teams/{teams[0]['id']}/aliases",
            headers=admin_headers,
            json={"alias": "A. FC"},
        )
        assert alias.status_code == 201
        match = client.post(
            "/api/v1/admin/matches",
            headers=admin_headers,
            json={
                "competition_id": competition["id"],
                "home_team_id": teams[0]["id"],
                "away_team_id": teams[1]["id"],
                "kickoff_date": "2026-10-20",
                "status": "SCHEDULED",
                "match_type": "UPCOMING",
            },
        ).json()
        assert client.delete(
            f"/api/v1/admin/matches/{match['id']}", headers=admin_headers
        ).status_code == 428
        assert client.delete(
            f"/api/v1/admin/matches/{match['id']}",
            headers=_headers(service.token(admin), confirm=True),
        ).status_code == 204
        source_match = client.post(
            "/api/v1/admin/matches",
            headers=admin_headers,
            json={
                "competition_id": competition["id"],
                "home_team_id": teams[2]["id"],
                "away_team_id": teams[1]["id"],
                "kickoff_date": "2026-10-21",
                "status": "SCHEDULED",
                "match_type": "UPCOMING",
            },
        ).json()
        merge = client.post(
            "/api/v1/admin/teams/merge",
            headers=admin_headers,
            json={"source_team_id": teams[2]["id"], "target_team_id": teams[0]["id"]},
        )
        assert merge.status_code == 200
        with app.state.database.connect(readonly=True) as conn:
            merged_home = conn.execute(
                "SELECT home_team_id FROM matches WHERE id=?", (source_match["id"],)
            ).fetchone()[0]
        assert merged_home == teams[0]["id"]

        with app.state.database.transaction() as conn:
            issue = conn.execute(
                """
                INSERT INTO data_quality_issues(
                    entity_type, entity_id, severity, code, message
                ) VALUES ('TEAM', ?, 'WARNING', 'TEST', 'Test') RETURNING id
                """,
                (str(teams[0]["id"]),),
            ).fetchone()[0]
        assert client.post(
            f"/api/v1/admin/quality/{issue}/resolve", headers=admin_headers
        ).json()["resolved_at"]
        updated_user = client.put(
            f"/api/v1/admin/users/{user['id']}",
            headers=admin_headers,
            json={"role": "ANALYST", "active": False},
        )
        assert updated_user.json()["role"] == "ANALYST"
        assert "password_hash" not in updated_user.json()
        audit = client.get("/api/v1/admin/audit", headers=admin_headers).json()
        assert {entry["action"] for entry in audit} >= {"CREATE", "DELETE", "MERGE", "RESOLVE"}


def test_admin_jobs_channels_scrapers_and_uploads(tmp_path: Path, monkeypatch) -> None:
    app, settings = _app(tmp_path)
    queued: list[tuple[str, list]] = []
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.celery,
            "send_task",
            lambda task, args: queued.append((task, args)),
        )
        service = AuthService(app.state.database, settings)
        admin = service.bootstrap_admin("admin@example.com", "secure-admin-password", "Admin")
        headers = _headers(service.token(admin))
        country = client.post(
            "/api/v1/admin/countries",
            headers=headers,
            json={"slug": "colombia", "name": "Colombia"},
        ).json()
        client.post(
            "/api/v1/admin/competitions",
            headers=headers,
            json={
                "country_id": country["id"],
                "slug": "primera-a",
                "name": "Primera A",
                "sport": "football",
            },
        )
        scraper = client.post(
            "/api/v1/admin/scrapers",
            headers=headers,
            json={
                "name": "Colombia Primera A",
                "country_slug": "colombia",
                "competition_slug": "primera-a",
            },
        )
        assert scraper.status_code == 201
        assert client.post("/api/v1/admin/scrapers/run", headers=headers).status_code == 202
        channel = client.put(
            "/api/v1/admin/channels/1",
            headers=headers,
            json={
                "name": "Local test",
                "webhook_url": "http://localhost:9999/events",
                "enabled": True,
            },
        )
        assert channel.status_code == 200
        record = [{"id": "one", "equipo_local": "A", "equipo_visitante": "B"}]
        upload = client.post(
            "/api/v1/admin/uploads/json",
            headers=headers,
            files={"file": ("feed.json", json.dumps(record), "application/json")},
            data={
                "country_slug": "colombia",
                "competition_slug": "primera-a",
                "captured_on": "2026-10-19",
            },
        )
        assert upload.status_code == 202
        assert upload.json()["job"]["status"] == "PENDING"
        assert client.post("/api/v1/admin/jobs/backtest", headers=headers).status_code == 202
        assert client.post("/api/v1/admin/jobs/train-xgboost", headers=headers).status_code == 202
        assert len(client.get("/api/v1/admin/jobs", headers=headers).json()) == 4
        assert len(queued) == 4
        preflight = client.get("/api/v1/admin/deployment/preflight", headers=headers).json()
        assert preflight["ready"] is False
        assert "FAIS_ENVIRONMENT must be production" in preflight["issues"]


def test_admin_accepts_only_a_valid_legacy_sqlite_upload(tmp_path: Path, monkeypatch) -> None:
    app, settings = _app(tmp_path)
    legacy = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE paises(id INTEGER PRIMARY KEY, nombre TEXT, codigo TEXT);
        CREATE TABLE competiciones(
            id INTEGER PRIMARY KEY, pais_id INTEGER, nombre TEXT, url TEXT
        );
        CREATE TABLE partidos(
            id TEXT, competicion_id INTEGER, tipo TEXT, fecha_hora TEXT,
            equipo_local TEXT, equipo_visitante TEXT, goles_local INTEGER,
            goles_visitante INTEGER, estado TEXT, jornada TEXT, link TEXT
        );
        """
    )
    conn.close()
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.celery, "send_task", lambda task, args: None)
        service = AuthService(app.state.database, settings)
        admin = service.bootstrap_admin("admin@example.com", "secure-admin-password", "Admin")
        with legacy.open("rb") as source:
            response = client.post(
                "/api/v1/admin/uploads/sqlite",
                headers=_headers(service.token(admin)),
                files={"file": ("legacy.sqlite", source, "application/vnd.sqlite3")},
            )
    assert response.status_code == 202
