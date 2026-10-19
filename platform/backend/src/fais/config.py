from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    redis_url: str
    cors_origins: tuple[str, ...]
    log_level: str
    auth_secret: str = "development-only-change-me"
    access_token_minutes: int = 480
    environment: str = "development"
    inbox_path: Path | None = None
    alert_webhook_url: str | None = None
    alert_webhook_token: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        default_db = Path(__file__).resolve().parents[3] / "data" / "fais.sqlite3"
        origins = os.getenv("FAIS_CORS_ORIGINS", "http://localhost:5173")
        return cls(
            database_path=Path(os.getenv("FAIS_DATABASE_PATH", str(default_db))).resolve(),
            redis_url=os.getenv("FAIS_REDIS_URL", "redis://127.0.0.1:6379/0"),
            cors_origins=tuple(x.strip() for x in origins.split(",") if x.strip()),
            log_level=os.getenv("FAIS_LOG_LEVEL", "INFO").upper(),
            auth_secret=os.getenv("FAIS_AUTH_SECRET", "development-only-change-me"),
            access_token_minutes=int(os.getenv("FAIS_ACCESS_TOKEN_MINUTES", "480")),
            environment=os.getenv("FAIS_ENVIRONMENT", "development").strip().lower(),
            inbox_path=Path(
                os.getenv("FAIS_INBOX_PATH", str(default_db.parent / "inbox"))
            ).resolve(),
            alert_webhook_url=os.getenv("FAIS_ALERT_WEBHOOK_URL") or None,
            alert_webhook_token=os.getenv("FAIS_ALERT_WEBHOOK_TOKEN") or None,
        )

    def production_issues(self) -> list[str]:
        """Return actionable errors without ever exposing secret values."""
        issues: list[str] = []
        if self.environment != "production":
            return issues
        if self.auth_secret == "development-only-change-me" or len(self.auth_secret) < 32:
            issues.append("FAIS_AUTH_SECRET must contain at least 32 random characters")
        if not self.cors_origins:
            issues.append("FAIS_CORS_ORIGINS must contain at least one HTTPS origin")
        for origin in self.cors_origins:
            parsed = urlparse(origin)
            if origin == "*" or parsed.scheme != "https" or not parsed.netloc:
                issues.append(f"CORS origin is not an absolute HTTPS URL: {origin}")
        if not self.database_path.is_absolute():
            issues.append("FAIS_DATABASE_PATH must be absolute")
        if urlparse(self.redis_url).scheme not in {"redis", "rediss"}:
            issues.append("FAIS_REDIS_URL must use redis:// or rediss://")
        if self.access_token_minutes < 5 or self.access_token_minutes > 1_440:
            issues.append("FAIS_ACCESS_TOKEN_MINUTES must be between 5 and 1440")
        if self.alert_webhook_url and urlparse(self.alert_webhook_url).scheme != "https":
            issues.append("FAIS_ALERT_WEBHOOK_URL must use HTTPS in production")
        return issues

    def validate_for_startup(self) -> None:
        issues = self.production_issues()
        if issues:
            raise ValueError("Invalid production configuration: " + "; ".join(issues))
