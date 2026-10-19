from __future__ import annotations

from pathlib import Path

import pytest

from fais.config import Settings


def test_production_rejects_default_secret_and_insecure_cors(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "fais.sqlite3",
        redis_url="redis://127.0.0.1:6379/0",
        cors_origins=("*", "http://sports.example.com"),
        log_level="INFO",
        environment="production",
    )
    with pytest.raises(ValueError, match="FAIS_AUTH_SECRET"):
        settings.validate_for_startup()
    assert len(settings.production_issues()) == 4


def test_secure_production_configuration_is_valid(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "fais.sqlite3",
        redis_url="redis://127.0.0.1:6379/0",
        cors_origins=("https://sports.example.com",),
        log_level="INFO",
        auth_secret="a" * 48,
        environment="production",
        public_domain="sports.example.com",
        allowed_hosts=("sports.example.com",),
    )
    settings.validate_for_startup()
    assert settings.production_issues() == []
