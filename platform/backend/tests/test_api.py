from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.config import Settings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "api.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
    )


def test_rest_health_and_overview(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        overview = client.get("/api/v1/overview")
        assert overview.status_code == 200
        assert overview.json()["counts"]["matches"] == 0
        readiness = client.get("/api/v1/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["database"] == "ok"
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "fais_http_requests_total" in metrics.text
        assert "fais_database_up 1" in metrics.text
        assert "fais_redis_up" in metrics.text


def test_graphql_overview(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/graphql",
            json={"query": "{ overview { openQualityIssues counts { matches teams } } }"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["overview"]["counts"] == {"matches": 0, "teams": 0}
