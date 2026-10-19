from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_systemd_services_are_native_and_hardened() -> None:
    service_dir = ROOT / "deploy/systemd"
    services = sorted(service_dir.glob("*.service"))
    assert {path.name for path in services} >= {
        "fais-api.service",
        "fais-worker.service",
        "fais-beat.service",
        "fais-redis.service",
        "fais-caddy.service",
    }
    for path in services:
        content = path.read_text(encoding="utf-8")
        assert "[Service]" in content
        assert "NoNewPrivileges=true" in content
        assert "PrivateTmp=true" in content
        assert "docker" not in content.lower()


def test_redis_is_local_only_and_persistent() -> None:
    content = (ROOT / "deploy/redis.conf").read_text(encoding="utf-8")
    assert "bind 127.0.0.1 ::1" in content
    assert "protected-mode yes" in content
    assert "appendonly yes" in content


def test_caddy_routes_api_graphql_websocket_and_spa() -> None:
    content = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8")
    for route in ("/api/*", "/graphql*", "/ws/*"):
        assert route in content
    assert "try_files {path} /index.html" in content


def test_prometheus_rules_cover_critical_dependencies() -> None:
    alerts = (ROOT / "deploy/prometheus/alerts.yml").read_text(encoding="utf-8")
    scrape = (ROOT / "deploy/prometheus/prometheus.yml").read_text(encoding="utf-8")
    expected = (
        "FaisApiDown",
        "FaisDatabaseUnavailable",
        "FaisRedisUnavailable",
        "FaisOutboxBacklog",
    )
    for alert in expected:
        assert f"alert: {alert}" in alerts
    assert 'targets: ["127.0.0.1:8000"]' in scrape


def test_native_install_scripts_are_container_free_and_strict() -> None:
    scripts = [
        ROOT / "deploy/install-native.sh",
        ROOT / "scripts/build_native_runtime.sh",
    ]
    for path in scripts:
        content = path.read_text(encoding="utf-8")
        assert "set -euo pipefail" in content
        assert "docker" not in content.lower()
        assert "podman" not in content.lower()
