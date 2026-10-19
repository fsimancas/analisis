from __future__ import annotations

import json
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from redis import Redis

from fais.auth import AuthService
from fais.db import Database

router = APIRouter(prefix="/api/v1")
bearer = HTTPBearer(auto_error=False)


class Registration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)


class Credentials(BaseModel):
    email: EmailStr
    password: str


class FavoriteInput(BaseModel):
    match_id: int | None = None
    team_id: int | None = None


class AlertInput(BaseModel):
    match_id: int
    event_type: Literal["KICKOFF", "GOAL", "FULL_TIME", "PREDICTION_READY", "ODDS_MOVEMENT"]
    threshold: float | None = None


def auth_service(request: Request) -> AuthService:
    return AuthService(request.app.state.database, request.app.state.settings)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> dict[str, Any]:
    user = service.user_from_token(credentials.credentials) if credentials else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def current_admin(
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator role required")
    try:
        redis = Redis.from_url(
            request.app.state.settings.redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        key = f"fais:admin-rate:{user['id']}:{int(time.time() // 60)}"
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 70)
        redis.close()
        if count > 120:
            raise HTTPException(status_code=429, detail="Administrative rate limit exceeded")
    except HTTPException:
        raise
    except Exception as error:
        if request.app.state.settings.environment == "production":
            raise HTTPException(
                status_code=503, detail="Administrative guard unavailable"
            ) from error
    return user


@router.post("/auth/register", status_code=201, tags=["identity"])
def register(body: Registration, service: Annotated[AuthService, Depends(auth_service)]):
    try:
        user = service.register(body.email, body.password, body.display_name)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"user": user, "access_token": service.token(user), "token_type": "bearer"}


@router.post("/auth/token", tags=["identity"])
def token(body: Credentials, service: Annotated[AuthService, Depends(auth_service)]):
    user = service.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": service.token(user), "token_type": "bearer"}


@router.get("/auth/me", tags=["identity"])
def me(user: Annotated[dict[str, Any], Depends(current_user)]):
    return user


@router.get("/admin/users", tags=["administration"])
def admin_users(
    request: Request,
    _: Annotated[dict[str, Any], Depends(current_admin)],
) -> list[dict[str, Any]]:
    database: Database = request.app.state.database
    with database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT id, email, display_name, role, active, created_at
            FROM users ORDER BY created_at DESC, id DESC LIMIT 500
            """
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/favorites", tags=["personalization"])
def favorites(request: Request, user: Annotated[dict[str, Any], Depends(current_user)]):
    database: Database = request.app.state.database
    with database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM favorites WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/favorites", status_code=201, tags=["personalization"])
def add_favorite(
    body: FavoriteInput,
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
):
    if (body.match_id is None) == (body.team_id is None):
        raise HTTPException(status_code=422, detail="Provide exactly one match_id or team_id")
    database: Database = request.app.state.database
    with database.transaction() as conn:
        conn.execute(
            """
            INSERT INTO favorites(user_id, match_id, team_id) VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (user["id"], body.match_id, body.team_id),
        )
        row = conn.execute(
            """
            SELECT * FROM favorites WHERE user_id=?
              AND match_id IS ? AND team_id IS ?
            """,
            (user["id"], body.match_id, body.team_id),
        ).fetchone()
    return dict(row)


@router.delete("/favorites/{favorite_id}", status_code=204, tags=["personalization"])
def delete_favorite(
    favorite_id: int,
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> None:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        changed = conn.execute(
            "DELETE FROM favorites WHERE id=? AND user_id=?", (favorite_id, user["id"])
        ).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="Favorite not found")


@router.get("/alerts", tags=["personalization"])
def alerts(request: Request, user: Annotated[dict[str, Any], Depends(current_user)]):
    database: Database = request.app.state.database
    with database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/alerts", status_code=201, tags=["personalization"])
def add_alert(
    body: AlertInput,
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
):
    database: Database = request.app.state.database
    with database.transaction() as conn:
        conn.execute(
            """
            INSERT INTO alerts(user_id, match_id, event_type, threshold)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, match_id, event_type)
            DO UPDATE SET threshold=excluded.threshold, active=1
            """,
            (user["id"], body.match_id, body.event_type, body.threshold),
        )
        row = conn.execute(
            "SELECT * FROM alerts WHERE user_id=? AND match_id=? AND event_type=?",
            (user["id"], body.match_id, body.event_type),
        ).fetchone()
    return dict(row)


@router.delete("/alerts/{alert_id}", status_code=204, tags=["personalization"])
def delete_alert(
    alert_id: int,
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> None:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        changed = conn.execute(
            "DELETE FROM alerts WHERE id=? AND user_id=?", (alert_id, user["id"])
        ).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.get("/notifications", tags=["personalization"])
def notifications(request: Request, user: Annotated[dict[str, Any], Depends(current_user)]):
    database: Database = request.app.state.database
    with database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT id, alert_id, event_key, title, payload, created_at, read_at
            FROM notifications WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT 100
            """,
            (user["id"],),
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["payload"] = json.loads(result["payload"])
    return results


@router.post("/notifications/{notification_id}/read", tags=["personalization"])
def read_notification(
    notification_id: int,
    request: Request,
    user: Annotated[dict[str, Any], Depends(current_user)],
):
    database: Database = request.app.state.database
    with database.transaction() as conn:
        changed = conn.execute(
            """
            UPDATE notifications SET read_at=CURRENT_TIMESTAMP
            WHERE id=? AND user_id=?
            """,
            (notification_id, user["id"]),
        ).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}
