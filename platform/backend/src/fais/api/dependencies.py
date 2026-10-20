from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from fais.api.identity import current_user
from fais.db import Database
from fais.db.repositories import SportsRepository


def get_repository(request: Request) -> SportsRepository:
    return request.app.state.repository


def get_database(request: Request) -> Database:
    return request.app.state.database


def competition_scope(
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> tuple[int, ...] | None:
    """Return None for global roles and an immutable competition allowlist for USER."""
    if user["role"] in {"ADMIN", "ANALYST"}:
        return None
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """SELECT competition_id FROM user_competition_permissions
            WHERE user_id=? ORDER BY competition_id""",
            (user["id"],),
        ).fetchall()
    return tuple(row[0] for row in rows)


def current_analyst(
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    if user["role"] not in {"ANALYST", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Analyst role required")
    return user
