from __future__ import annotations

import hashlib
import ipaddress
import json
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from socket import getaddrinfo
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from celery import Celery
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from fais.api.identity import current_admin
from fais.db import Database
from fais.ingestion.legacy_sqlite import normalize_name
from fais.jobs import JobStore

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
Admin = Annotated[dict[str, Any], Depends(current_admin)]
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class CountryInput(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    name: str = Field(min_length=2, max_length=120)


class CompetitionInput(BaseModel):
    country_id: int
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=2, max_length=160)
    sport: str = Field(default="football", min_length=2, max_length=40)
    gender: str | None = Field(default=None, max_length=30)
    tier: str | None = Field(default=None, max_length=30)
    active: bool = True


class TeamInput(BaseModel):
    country_id: int
    canonical_name: str = Field(min_length=2, max_length=160)


class MatchInput(BaseModel):
    competition_id: int
    home_team_id: int
    away_team_id: int
    kickoff_utc: str | None = Field(default=None, max_length=40)
    kickoff_date: date | None = None
    kickoff_raw: str | None = Field(default=None, max_length=100)
    round_name: str | None = Field(default=None, max_length=100)
    status: Literal[
        "SCHEDULED", "LIVE", "FINISHED", "POSTPONED", "SUSPENDED", "CANCELLED", "UNKNOWN"
    ]
    match_type: Literal["RESULT", "UPCOMING"]
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)

    @field_validator("away_team_id")
    @classmethod
    def teams_must_differ(cls, value: int, info):
        if value == info.data.get("home_team_id"):
            raise ValueError("Home and away teams must differ")
        return value

    @field_validator("away_score")
    @classmethod
    def scores_are_paired(cls, value: int | None, info):
        if (value is None) != (info.data.get("home_score") is None):
            raise ValueError("Both scores must be provided together")
        return value


class AliasInput(BaseModel):
    alias: str = Field(min_length=2, max_length=160)
    provider_id: int | None = None


class MergeTeamsInput(BaseModel):
    source_team_id: int
    target_team_id: int


class UserUpdate(BaseModel):
    role: Literal["USER", "ANALYST", "ADMIN"]
    active: bool


class ChannelInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    webhook_url: str = Field(min_length=8, max_length=500)
    enabled: bool = False


class ScraperInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    country_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    competition_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    enabled: bool = True


class ReviewInput(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=1000)


def _row(row) -> dict[str, Any] | None:
    return dict(row) if row else None


def _audit(
    conn,
    request: Request,
    actor: dict[str, Any],
    action: str,
    entity_type: str,
    entity_id: Any,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    remote = request.client.host if request.client else None
    conn.execute(
        """
        INSERT INTO audit_log(
            actor_user_id, action, entity_type, entity_id,
            before_payload, after_payload, remote_address
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor["id"],
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
            remote,
        ),
    )


def _delete(conn, table: str, identifier: int, request: Request, actor: dict) -> None:
    before = _row(conn.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone())
    if not before:
        raise HTTPException(status_code=404, detail=f"{table} record not found")
    try:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (identifier,))
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Record is still referenced") from error
    _audit(conn, request, actor, "DELETE", table, identifier, before=before)


def _require_destructive_confirmation(request: Request) -> None:
    if request.headers.get("X-Confirm-Action") != "delete":
        raise HTTPException(status_code=428, detail="X-Confirm-Action: delete is required")


@router.get("/summary")
def summary(request: Request, _: Admin) -> dict[str, Any]:
    database: Database = request.app.state.database
    with database.connect(readonly=True) as conn:
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "countries",
                "competitions",
                "teams",
                "matches",
                "users",
                "jobs",
                "admin_uploads",
                "audit_log",
            )
        }
        counts["open_quality_issues"] = conn.execute(
            "SELECT count(*) FROM data_quality_issues WHERE resolved_at IS NULL"
        ).fetchone()[0]
    return counts


@router.get("/countries")
def countries(request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM countries ORDER BY name")]


@router.post("/countries", status_code=201)
def create_country(body: CountryInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        try:
            row = conn.execute(
                "INSERT INTO countries(slug, name) VALUES (?, ?) RETURNING *",
                (body.slug, body.name.strip()),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Country slug already exists") from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "countries", row["id"], after=result)
    return result


@router.put("/countries/{identifier}")
def update_country(identifier: int, body: CountryInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(conn.execute("SELECT * FROM countries WHERE id=?", (identifier,)).fetchone())
        if not before:
            raise HTTPException(status_code=404, detail="Country not found")
        conn.execute(
            "UPDATE countries SET slug=?, name=? WHERE id=?",
            (body.slug, body.name.strip(), identifier),
        )
        after = dict(conn.execute("SELECT * FROM countries WHERE id=?", (identifier,)).fetchone())
        _audit(conn, request, actor, "UPDATE", "countries", identifier, before, after)
    return after


@router.delete("/countries/{identifier}", status_code=204)
def delete_country(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "countries", identifier, request, actor)


@router.get("/competitions")
def competitions(request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT c.*, co.name AS country FROM competitions c
            LEFT JOIN countries co ON co.id=c.country_id ORDER BY c.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/competitions", status_code=201)
def create_competition(body: CompetitionInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO competitions(country_id, slug, name, sport, gender, tier, active)
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *
                """,
                (
                    body.country_id,
                    body.slug,
                    body.name.strip(),
                    body.sport,
                    body.gender,
                    body.tier,
                    int(body.active),
                ),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="Invalid or duplicate competition"
            ) from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "competitions", row["id"], after=result)
    return result


@router.put("/competitions/{identifier}")
def update_competition(
    identifier: int, body: CompetitionInput, request: Request, actor: Admin
) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(
            conn.execute("SELECT * FROM competitions WHERE id=?", (identifier,)).fetchone()
        )
        if not before:
            raise HTTPException(status_code=404, detail="Competition not found")
        try:
            conn.execute(
                """
                UPDATE competitions SET country_id=?, slug=?, name=?, sport=?, gender=?,
                    tier=?, active=? WHERE id=?
                """,
                (
                    body.country_id,
                    body.slug,
                    body.name.strip(),
                    body.sport,
                    body.gender,
                    body.tier,
                    int(body.active),
                    identifier,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="Invalid or duplicate competition"
            ) from error
        after = dict(
            conn.execute("SELECT * FROM competitions WHERE id=?", (identifier,)).fetchone()
        )
        _audit(conn, request, actor, "UPDATE", "competitions", identifier, before, after)
    return after


@router.delete("/competitions/{identifier}", status_code=204)
def delete_competition(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "competitions", identifier, request, actor)


@router.get("/teams")
def teams(request: Request, _: Admin, search: str = "", limit: int = 200) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT t.*, c.name AS country FROM teams t
            LEFT JOIN countries c ON c.id=t.country_id
            WHERE t.canonical_name LIKE ? ORDER BY t.canonical_name LIMIT ?
            """,
            (f"%{search}%", min(max(limit, 1), 500)),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/teams", status_code=201)
def create_team(body: TeamInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO teams(canonical_name, normalized_name, country_id)
                VALUES (?, ?, ?) RETURNING *
                """,
                (body.canonical_name.strip(), normalize_name(body.canonical_name), body.country_id),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Invalid or duplicate team") from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "teams", row["id"], after=result)
    return result


@router.put("/teams/{identifier}")
def update_team(identifier: int, body: TeamInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(conn.execute("SELECT * FROM teams WHERE id=?", (identifier,)).fetchone())
        if not before:
            raise HTTPException(status_code=404, detail="Team not found")
        try:
            conn.execute(
                """
                UPDATE teams SET canonical_name=?, normalized_name=?, country_id=? WHERE id=?
                """,
                (
                    body.canonical_name.strip(),
                    normalize_name(body.canonical_name),
                    body.country_id,
                    identifier,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Invalid or duplicate team") from error
        after = dict(conn.execute("SELECT * FROM teams WHERE id=?", (identifier,)).fetchone())
        _audit(conn, request, actor, "UPDATE", "teams", identifier, before, after)
    return after


@router.delete("/teams/{identifier}", status_code=204)
def delete_team(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "teams", identifier, request, actor)


@router.post("/teams/{identifier}/aliases", status_code=201)
def add_alias(identifier: int, body: AliasInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        team = conn.execute("SELECT country_id FROM teams WHERE id=?", (identifier,)).fetchone()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        try:
            row = conn.execute(
                """
                INSERT INTO team_aliases(
                    team_id, provider_id, country_id, alias, normalized_alias
                ) VALUES (?, ?, ?, ?, ?) RETURNING *
                """,
                (
                    identifier,
                    body.provider_id,
                    team["country_id"],
                    body.alias.strip(),
                    normalize_name(body.alias),
                ),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Alias already exists") from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "team_aliases", row["id"], after=result)
    return result


@router.get("/teams/{identifier}/aliases")
def aliases(identifier: int, request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM team_aliases WHERE team_id=? ORDER BY alias", (identifier,)
        ).fetchall()
    return [dict(row) for row in rows]


@router.delete("/aliases/{identifier}", status_code=204)
def delete_alias(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "team_aliases", identifier, request, actor)


@router.post("/teams/merge")
def merge_teams(body: MergeTeamsInput, request: Request, actor: Admin) -> dict:
    if body.source_team_id == body.target_team_id:
        raise HTTPException(status_code=422, detail="Source and target must differ")
    database: Database = request.app.state.database
    with database.transaction() as conn:
        source = _row(
            conn.execute("SELECT * FROM teams WHERE id=?", (body.source_team_id,)).fetchone()
        )
        target = _row(
            conn.execute("SELECT * FROM teams WHERE id=?", (body.target_team_id,)).fetchone()
        )
        if not source or not target:
            raise HTTPException(status_code=404, detail="Source or target team not found")
        direct = conn.execute(
            """
            SELECT count(*) FROM matches
            WHERE (home_team_id=? AND away_team_id=?) OR (home_team_id=? AND away_team_id=?)
            """,
            (
                body.source_team_id,
                body.target_team_id,
                body.target_team_id,
                body.source_team_id,
            ),
        ).fetchone()[0]
        if direct:
            raise HTTPException(
                status_code=409, detail="Teams have played each other; merge is unsafe"
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO team_aliases(
                team_id, provider_id, country_id, alias, normalized_alias
            ) SELECT ?, provider_id, country_id, alias, normalized_alias
              FROM team_aliases WHERE team_id=?
            """,
            (body.target_team_id, body.source_team_id),
        )
        conn.execute("DELETE FROM team_aliases WHERE team_id=?", (body.source_team_id,))
        conn.execute(
            """
            INSERT OR IGNORE INTO team_provider_refs(
                team_id, provider_id, external_id, external_name
            ) SELECT ?, provider_id, external_id, external_name
              FROM team_provider_refs WHERE team_id=?
            """,
            (body.target_team_id, body.source_team_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO favorites(user_id, team_id)
            SELECT user_id, ? FROM favorites WHERE team_id=?
            """,
            (body.target_team_id, body.source_team_id),
        )
        conn.execute(
            "UPDATE matches SET home_team_id=? WHERE home_team_id=?",
            tuple(reversed((body.source_team_id, body.target_team_id))),
        )
        conn.execute(
            "UPDATE matches SET away_team_id=? WHERE away_team_id=?",
            tuple(reversed((body.source_team_id, body.target_team_id))),
        )
        conn.execute("DELETE FROM feature_snapshots WHERE team_id=?", (body.source_team_id,))
        conn.execute("DELETE FROM favorites WHERE team_id=?", (body.source_team_id,))
        conn.execute("DELETE FROM team_provider_refs WHERE team_id=?", (body.source_team_id,))
        conn.execute(
            """
            DELETE FROM data_quality_issues AS source
            WHERE source.entity_type='TEAM' AND source.entity_id=?
              AND EXISTS (
                SELECT 1 FROM data_quality_issues AS target
                WHERE target.entity_type='TEAM' AND target.entity_id=?
                  AND target.code=source.code
                  AND target.source_provider_id IS source.source_provider_id
              )
            """,
            (str(body.source_team_id), str(body.target_team_id)),
        )
        conn.execute(
            """
            UPDATE data_quality_issues SET entity_id=?
            WHERE entity_type='TEAM' AND entity_id=?
            """,
            (str(body.target_team_id), str(body.source_team_id)),
        )
        conn.execute("DELETE FROM teams WHERE id=?", (body.source_team_id,))
        _audit(
            conn,
            request,
            actor,
            "MERGE",
            "teams",
            body.target_team_id,
            before={"source": source, "target": target},
            after={"target": target},
        )
    return {"merged": body.source_team_id, "into": body.target_team_id}


@router.get("/matches")
def admin_matches(request: Request, _: Admin, limit: int = 200) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT m.*, c.name AS competition, h.canonical_name AS home_team,
                   a.canonical_name AS away_team
            FROM matches m JOIN competitions c ON c.id=m.competition_id
            JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
            ORDER BY COALESCE(m.kickoff_utc, m.kickoff_date) DESC, m.id DESC LIMIT ?
            """,
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [dict(row) for row in rows]


def _match_values(body: MatchInput) -> tuple:
    return (
        body.competition_id,
        body.home_team_id,
        body.away_team_id,
        body.kickoff_utc,
        body.kickoff_date.isoformat() if body.kickoff_date else None,
        body.kickoff_raw,
        body.round_name,
        body.status,
        body.match_type,
        body.home_score,
        body.away_score,
    )


@router.post("/matches", status_code=201)
def create_match(body: MatchInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, kickoff_utc, kickoff_date,
                    kickoff_raw, round_name, status, match_type, home_score, away_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *
                """,
                _match_values(body),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="Invalid match references or values"
            ) from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "matches", row["id"], after=result)
    return result


@router.put("/matches/{identifier}")
def update_match(identifier: int, body: MatchInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(conn.execute("SELECT * FROM matches WHERE id=?", (identifier,)).fetchone())
        if not before:
            raise HTTPException(status_code=404, detail="Match not found")
        try:
            conn.execute(
                """
                UPDATE matches SET competition_id=?, home_team_id=?, away_team_id=?,
                    kickoff_utc=?, kickoff_date=?, kickoff_raw=?, round_name=?, status=?,
                    match_type=?, home_score=?, away_score=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (*_match_values(body), identifier),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="Invalid match references or values"
            ) from error
        after = dict(conn.execute("SELECT * FROM matches WHERE id=?", (identifier,)).fetchone())
        _audit(conn, request, actor, "UPDATE", "matches", identifier, before, after)
    return after


@router.delete("/matches/{identifier}", status_code=204)
def delete_match(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "matches", identifier, request, actor)


@router.post("/quality/{identifier}/resolve")
def resolve_quality(identifier: int, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(
            conn.execute("SELECT * FROM data_quality_issues WHERE id=?", (identifier,)).fetchone()
        )
        if not before:
            raise HTTPException(status_code=404, detail="Quality issue not found")
        conn.execute(
            "UPDATE data_quality_issues SET resolved_at=CURRENT_TIMESTAMP WHERE id=?",
            (identifier,),
        )
        after = dict(
            conn.execute("SELECT * FROM data_quality_issues WHERE id=?", (identifier,)).fetchone()
        )
        _audit(conn, request, actor, "RESOLVE", "data_quality_issues", identifier, before, after)
    return after


@router.put("/users/{identifier}")
def update_user(identifier: int, body: UserUpdate, request: Request, actor: Admin) -> dict:
    if identifier == actor["id"] and (not body.active or body.role != "ADMIN"):
        raise HTTPException(
            status_code=409, detail="Administrators cannot demote or block themselves"
        )
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(conn.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone())
        if not before:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute(
            "UPDATE users SET role=?, active=? WHERE id=?",
            (body.role, int(body.active), identifier),
        )
        after = dict(conn.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone())
        after.pop("password_hash", None)
        safe_before = dict(before)
        safe_before.pop("password_hash", None)
        _audit(conn, request, actor, "UPDATE", "users", identifier, safe_before, after)
    return after


def _validate_webhook(request: Request, url: str) -> None:
    parsed = urlparse(url)
    settings = request.app.state.settings
    if parsed.scheme not in (
        {"https"} if settings.environment == "production" else {"http", "https"}
    ):
        raise HTTPException(status_code=422, detail="Webhook URL scheme is not allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=422, detail="Webhook hostname is required")
    allowed = settings.webhook_allowed_hosts
    if settings.environment == "production" and parsed.hostname not in allowed:
        raise HTTPException(
            status_code=422, detail="Webhook host is not in FAIS_WEBHOOK_ALLOWED_HOSTS"
        )
    try:
        addresses = {item[4][0] for item in getaddrinfo(parsed.hostname, parsed.port or 443)}
    except OSError as error:
        raise HTTPException(
            status_code=422, detail="Webhook hostname cannot be resolved"
        ) from error
    if settings.environment == "production" and any(
        ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback
        for address in addresses
    ):
        raise HTTPException(status_code=422, detail="Private webhook destinations are forbidden")


@router.get("/channels")
def channels(request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM alert_channels ORDER BY name")]


@router.put("/channels/{identifier}")
def update_channel(identifier: int, body: ChannelInput, request: Request, actor: Admin) -> dict:
    _validate_webhook(request, body.webhook_url)
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(
            conn.execute("SELECT * FROM alert_channels WHERE id=?", (identifier,)).fetchone()
        )
        conn.execute(
            """
            INSERT INTO alert_channels(id, name, channel_type, webhook_url, enabled)
            VALUES (?, ?, 'WEBHOOK', ?, ?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, webhook_url=excluded.webhook_url,
                enabled=excluded.enabled, updated_at=CURRENT_TIMESTAMP
            """,
            (identifier, body.name, body.webhook_url, int(body.enabled)),
        )
        after = dict(
            conn.execute("SELECT * FROM alert_channels WHERE id=?", (identifier,)).fetchone()
        )
        _audit(conn, request, actor, "UPSERT", "alert_channels", identifier, before, after)
    return after


@router.get("/scrapers")
def scrapers(request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM scraper_sources ORDER BY name")]


@router.post("/scrapers", status_code=201)
def create_scraper(body: ScraperInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO scraper_sources(name, country_slug, competition_slug, enabled)
                VALUES (?, ?, ?, ?) RETURNING *
                """,
                (body.name, body.country_slug, body.competition_slug, int(body.enabled)),
            ).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Scraper source already exists") from error
        result = dict(row)
        _audit(conn, request, actor, "CREATE", "scraper_sources", row["id"], after=result)
    return result


@router.put("/scrapers/{identifier}")
def update_scraper(identifier: int, body: ScraperInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        before = _row(
            conn.execute("SELECT * FROM scraper_sources WHERE id=?", (identifier,)).fetchone()
        )
        if not before:
            raise HTTPException(status_code=404, detail="Scraper source not found")
        conn.execute(
            """
            UPDATE scraper_sources SET name=?, country_slug=?, competition_slug=?, enabled=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (
                body.name,
                body.country_slug,
                body.competition_slug,
                int(body.enabled),
                identifier,
            ),
        )
        after = dict(
            conn.execute("SELECT * FROM scraper_sources WHERE id=?", (identifier,)).fetchone()
        )
        _audit(conn, request, actor, "UPDATE", "scraper_sources", identifier, before, after)
    return after


@router.delete("/scrapers/{identifier}", status_code=204)
def delete_scraper(identifier: int, request: Request, actor: Admin) -> None:
    _require_destructive_confirmation(request)
    with request.app.state.database.transaction() as conn:
        _delete(conn, "scraper_sources", identifier, request, actor)


def _queue_job(request: Request, job_type: str, task: str, args: list | None = None) -> dict:
    database: Database = request.app.state.database
    store = JobStore(database)
    job = store.create(job_type, {"source": "admin"})
    celery: Celery = request.app.state.celery
    try:
        celery.send_task(task, args=[*(args or []), job["id"]])
    except Exception as error:
        store.failed(job["id"], f"Queue unavailable: {error}")
        raise HTTPException(status_code=503, detail="Worker queue unavailable") from error
    return store.get(job["id"]) or job


@router.post("/scrapers/run", status_code=202)
def run_scrapers(request: Request, actor: Admin) -> dict:
    job = _queue_job(request, "SCAN_INBOX", "fais.workers.tasks.scan_inbox")
    with request.app.state.database.transaction() as conn:
        _audit(conn, request, actor, "RUN", "scraper_sources", None, after={"job_id": job["id"]})
    return job


@router.get("/jobs")
def jobs(request: Request, _: Admin, limit: int = 200) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (min(max(limit, 1), 500),)
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
    return results


@router.post("/jobs/backtest", status_code=202)
def enqueue_backtest(request: Request, actor: Admin) -> dict:
    job = _queue_job(request, "BACKTEST", "fais.workers.tasks.run_backtest", [3])
    with request.app.state.database.transaction() as conn:
        _audit(conn, request, actor, "RUN", "backtests", job["id"], after={"job_id": job["id"]})
    return job


@router.post("/jobs/train-xgboost", status_code=202)
def enqueue_training(request: Request, actor: Admin) -> dict:
    job = _queue_job(request, "TRAIN_XGBOOST", "fais.workers.tasks.train_xgboost", [False])
    with request.app.state.database.transaction() as conn:
        _audit(
            conn, request, actor, "RUN", "model_training", job["id"], after={"job_id": job["id"]}
        )
    return job


async def _store_upload(
    upload: UploadFile, root: Path, suffixes: set[str]
) -> tuple[str, Path, int, str]:
    filename = Path(upload.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in suffixes:
        accepted = ", ".join(sorted(suffixes))
        raise HTTPException(status_code=415, detail=f"Only {accepted} files are accepted")
    identifier = uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{identifier}{suffix}"
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("xb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds 25 MiB")
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return filename, path, size, digest.hexdigest()


def _record_upload(
    database: Database,
    identifier: str,
    actor: dict,
    filename: str,
    path: Path,
    kind: str,
    size: int,
    digest: str,
) -> None:
    with database.transaction() as conn:
        conn.execute(
            """
            INSERT INTO admin_uploads(
                id, user_id, filename, stored_path, upload_type, size_bytes, sha256, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'STAGED')
            """,
            (identifier, actor["id"], filename, str(path), kind, size, digest),
        )


def _queue_upload(request: Request, identifier: str, task: str, args: list, job_type: str) -> dict:
    job = JobStore(request.app.state.database).create(job_type, {"upload_id": identifier})
    try:
        request.app.state.celery.send_task(task, args=[*args, job["id"]])
    except Exception as error:
        JobStore(request.app.state.database).failed(job["id"], f"Queue unavailable: {error}")
        with request.app.state.database.transaction() as conn:
            conn.execute(
                "UPDATE admin_uploads SET status='FAILED', error=? WHERE id=?",
                (str(error)[:1000], identifier),
            )
        raise HTTPException(status_code=503, detail="Worker queue unavailable") from error
    with request.app.state.database.transaction() as conn:
        conn.execute(
            "UPDATE admin_uploads SET status='QUEUED', job_id=? WHERE id=?",
            (job["id"], identifier),
        )
    return JobStore(request.app.state.database).get(job["id"]) or job


@router.post("/uploads/json", status_code=202)
async def upload_json(
    request: Request,
    actor: Admin,
    file: Annotated[UploadFile, File()],
    country_slug: Annotated[str, Form()],
    competition_slug: Annotated[str, Form()],
    captured_on: Annotated[date, Form()],
) -> dict:
    database: Database = request.app.state.database
    root = database.path.parent / "uploads"
    filename, path, size, digest = await _store_upload(file, root, {".json"})
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError("root must be an array")
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Invalid JSON feed: {error}") from error
    identifier = path.stem
    _record_upload(database, identifier, actor, filename, path, "JSON", size, digest)
    job = _queue_upload(
        request,
        identifier,
        "fais.workers.tasks.ingest_json",
        [str(path), country_slug, competition_slug, captured_on.isoformat()],
        "INGEST_JSON",
    )
    with database.transaction() as conn:
        _audit(
            conn, request, actor, "UPLOAD", "admin_uploads", identifier, after={"job_id": job["id"]}
        )
    return {"upload_id": identifier, "job": job}


@router.post("/uploads/sqlite", status_code=202)
async def upload_sqlite(
    request: Request,
    actor: Admin,
    file: Annotated[UploadFile, File()],
) -> dict:
    database: Database = request.app.state.database
    root = database.path.parent / "uploads"
    filename, path, size, digest = await _store_upload(file, root, {".db", ".sqlite", ".sqlite3"})
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        if check != "ok" or "partidos" not in tables:
            raise ValueError("not a valid legacy FAIS database")
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Invalid SQLite upload: {error}") from error
    identifier = path.stem
    _record_upload(database, identifier, actor, filename, path, "SQLITE", size, digest)
    job = _queue_upload(
        request,
        identifier,
        "fais.workers.tasks.import_legacy",
        [str(path)],
        "IMPORT_LEGACY",
    )
    with database.transaction() as conn:
        _audit(
            conn, request, actor, "UPLOAD", "admin_uploads", identifier, after={"job_id": job["id"]}
        )
    return {"upload_id": identifier, "job": job}


@router.get("/uploads")
def uploads(request: Request, _: Admin) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM admin_uploads ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/models/{identifier}/review")
def review_model(identifier: int, body: ReviewInput, request: Request, actor: Admin) -> dict:
    database: Database = request.app.state.database
    with database.transaction() as conn:
        model = _row(
            conn.execute("SELECT * FROM model_versions WHERE id=?", (identifier,)).fetchone()
        )
        if not model:
            raise HTTPException(status_code=404, detail="Model version not found")
        metrics = json.loads(model["metrics"])
        if body.decision == "APPROVED":
            promotable = model["algorithm"] == "regularized-poisson" or metrics.get("promotable")
            if not promotable:
                raise HTTPException(
                    status_code=409, detail="Model has not passed promotion criteria"
                )
            conn.execute("UPDATE model_versions SET active=0 WHERE name=?", (model["name"],))
            conn.execute("UPDATE model_versions SET active=1 WHERE id=?", (identifier,))
        elif model["active"]:
            raise HTTPException(status_code=409, detail="The active model cannot be rejected")
        conn.execute(
            """
            INSERT INTO model_reviews(model_version_id, reviewer_user_id, decision, notes)
            VALUES (?, ?, ?, ?)
            """,
            (identifier, actor["id"], body.decision, body.notes),
        )
        after = dict(
            conn.execute("SELECT * FROM model_versions WHERE id=?", (identifier,)).fetchone()
        )
        _audit(conn, request, actor, body.decision, "model_versions", identifier, model, after)
    after["metrics"] = json.loads(after["metrics"])
    return after


@router.get("/audit")
def audit_log(request: Request, _: Admin, limit: int = 200) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT a.*, u.email AS actor_email FROM audit_log a
            LEFT JOIN users u ON u.id=a.actor_user_id
            ORDER BY a.created_at DESC, a.id DESC LIMIT ?
            """,
            (min(max(limit, 1), 1000),),
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["before_payload"] = (
            json.loads(result["before_payload"]) if result["before_payload"] else None
        )
        result["after_payload"] = (
            json.loads(result["after_payload"]) if result["after_payload"] else None
        )
    return results


@router.get("/deployment/preflight")
def deployment_preflight(request: Request, _: Admin) -> dict:
    settings = request.app.state.settings
    issues = settings.deployment_issues()
    return {
        "ready": not issues,
        "environment": settings.environment,
        "domain": settings.public_domain,
        "database": str(settings.database_path),
        "redis": settings.redis_url.rsplit("@", 1)[-1],
        "issues": issues,
        "systemd_activation_required": True,
        "dns_verification_required": bool(settings.public_domain),
    }
