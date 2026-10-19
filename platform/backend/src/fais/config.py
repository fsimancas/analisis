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
    public_domain: str | None = None
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    webhook_allowed_hosts: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        default_db = Path(__file__).resolve().parents[3] / "data" / "fais.sqlite3"
        origins = os.getenv("FAIS_CORS_ORIGINS", "http://localhost:5173")
        public_domain = os.getenv("FAIS_DOMAIN") or None
        default_hosts = (
            f"{public_domain},localhost,127.0.0.1"
            if public_domain
            else "localhost,127.0.0.1,testserver"
        )
        allowed_hosts = os.getenv("FAIS_ALLOWED_HOSTS", default_hosts)
        webhook_hosts = os.getenv("FAIS_WEBHOOK_ALLOWED_HOSTS", "")
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
            public_domain=public_domain,
            allowed_hosts=tuple(x.strip() for x in allowed_hosts.split(",") if x.strip()),
            webhook_allowed_hosts=tuple(
                x.strip().casefold() for x in webhook_hosts.split(",") if x.strip()
            ),
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
        if (
            not self.public_domain
            or self.public_domain in {"localhost", "127.0.0.1"}
            or "." not in self.public_domain
        ):
            issues.append("FAIS_DOMAIN must contain a public DNS hostname")
        elif f"https://{self.public_domain}" not in self.cors_origins:
            issues.append("FAIS_CORS_ORIGINS must include the public HTTPS domain")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            issues.append("FAIS_ALLOWED_HOSTS must explicitly list trusted hostnames")
        return issues

    def validate_for_startup(self) -> None:
        issues = self.production_issues()
        if issues:
            raise ValueError("Invalid production configuration: " + "; ".join(issues))

    def deployment_issues(self) -> list[str]:
        if self.environment != "production":
            return ["FAIS_ENVIRONMENT must be production"]
        return self.production_issues()
