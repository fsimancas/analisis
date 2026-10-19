from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from fais.config import Settings
from fais.db import Database

passwords = PasswordHash.recommended()


class AuthService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    def register(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        normalized = email.strip().casefold()
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters")
        with self.database.transaction() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO users(email, password_hash, display_name)
                    VALUES (?, ?, ?) RETURNING id, email, display_name, role, active, created_at
                    """,
                    (normalized, passwords.hash(password), display_name.strip()),
                ).fetchone()
            except Exception as error:
                if "UNIQUE constraint failed" in str(error):
                    raise ValueError("Email is already registered") from error
                raise
        return dict(row)

    def bootstrap_admin(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        """Create or deliberately promote one administrator from a trusted CLI."""
        normalized = email.strip().casefold()
        if len(password) < 12:
            raise ValueError("Administrator password must contain at least 12 characters")
        if not normalized or "@" not in normalized:
            raise ValueError("A valid administrator email is required")
        with self.database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users(email, password_hash, display_name, role, active)
                VALUES (?, ?, ?, 'ADMIN', 1)
                ON CONFLICT(email) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    display_name=excluded.display_name,
                    role='ADMIN', active=1
                """,
                (normalized, passwords.hash(password), display_name.strip()),
            )
            row = conn.execute(
                """
                SELECT id, email, display_name, role, active, created_at
                FROM users WHERE email=? COLLATE NOCASE
                """,
                (normalized,),
            ).fetchone()
        return dict(row)

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        with self.database.connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email=? COLLATE NOCASE AND active=1",
                (email.strip(),),
            ).fetchone()
        if not row or not passwords.verify(password, row["password_hash"]):
            return None
        return dict(row)

    def token(self, user: dict[str, Any]) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(user["id"]),
                "role": user["role"],
                "iat": now,
                "exp": now + timedelta(minutes=self.settings.access_token_minutes),
            },
            self.settings.auth_secret,
            algorithm="HS256",
        )

    def user_from_token(self, token: str) -> dict[str, Any] | None:
        try:
            payload = jwt.decode(token, self.settings.auth_secret, algorithms=["HS256"])
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            return None
        with self.database.connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, email, display_name, role, active, created_at
                FROM users WHERE id=? AND active=1
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
