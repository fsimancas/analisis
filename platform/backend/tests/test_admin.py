from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.auth import AuthService
from fais.config import Settings


def test_only_an_administrator_can_list_users(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "admin.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        ordinary = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "ordinary-user-password",
                "display_name": "User",
            },
        ).json()
        service = AuthService(app.state.database, settings)
        admin = service.bootstrap_admin(
            "admin@example.com", "secure-admin-password", "Administrator"
        )
        admin_token = service.token(admin)

        ordinary_response = client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {ordinary['access_token']}"},
        )
        admin_response = client.get(
            "/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"}
        )

    assert ordinary_response.status_code == 403
    assert admin_response.status_code == 200
    assert {user["role"] for user in admin_response.json()} == {"USER", "ADMIN"}
