from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from fais.api.dependencies import competition_scope, current_analyst, get_repository
from fais.db.repositories import SportsRepository

router = APIRouter(prefix="/api/v1", tags=["match-details"])
Scope = Annotated[tuple[int, ...] | None, Depends(competition_scope)]
Analyst = Annotated[dict[str, Any], Depends(current_analyst)]


class LineupPlayerInput(BaseModel):
    player_id: int
    shirt_number: int | None = Field(default=None, ge=0, le=99)
    position_code: str | None = Field(default=None, max_length=20)
    starter: bool = True
    field_x: float | None = Field(default=None, ge=0, le=100)
    field_y: float | None = Field(default=None, ge=0, le=100)


class LineupInput(BaseModel):
    team_id: int
    status: Literal["PROBABLE", "CONFIRMED", "FINAL"] = "CONFIRMED"
    formation_code: str | None = Field(default=None, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    announced_at: str | None = Field(default=None, max_length=40)
    players: list[LineupPlayerInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_players(self):
        identifiers = [player.player_id for player in self.players]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Lineup players must be unique")
        return self


def _json(value: str | None) -> Any:
    return json.loads(value) if value else None


@router.get("/matches/{match_id}/details")
def match_details(
    match_id: int,
    request: Request,
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
) -> dict:
    match = repo.match(match_id, scope)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    with request.app.state.database.connect(readonly=True) as conn:
        lineup_rows = conn.execute(
            """SELECT l.*, t.canonical_name AS team, f.code AS formation
            FROM lineups l JOIN teams t ON t.id=l.team_id
            LEFT JOIN formations f ON f.id=l.formation_id
            WHERE l.match_id=? ORDER BY l.team_id, l.status""",
            (match_id,),
        ).fetchall()
        lineups = []
        for lineup in lineup_rows:
            item = dict(lineup)
            item["players"] = [
                dict(row)
                for row in conn.execute(
                    """SELECT lp.*, p.canonical_name AS player, p.primary_position
                    FROM lineup_players lp JOIN players p ON p.id=lp.player_id
                    WHERE lp.lineup_id=? ORDER BY lp.starter DESC, lp.id""",
                    (lineup["id"],),
                )
            ]
            lineups.append(item)
        referees = [
            dict(row)
            for row in conn.execute(
                """SELECT r.id, r.canonical_name AS name, r.category, mr.role
                FROM match_referees mr JOIN referees r ON r.id=mr.referee_id
                WHERE mr.match_id=? ORDER BY mr.role""",
                (match_id,),
            )
        ]
        events = [
            {**dict(row), "payload": _json(row["payload"])}
            for row in conn.execute(
                """SELECT e.*, t.canonical_name AS team, p.canonical_name AS player
                FROM match_events e LEFT JOIN teams t ON t.id=e.team_id
                LEFT JOIN players p ON p.id=e.player_id WHERE e.match_id=?
                ORDER BY e.minute, e.added_minute, e.id""",
                (match_id,),
            )
        ]
        statistics = [
            dict(row)
            for row in conn.execute(
                """SELECT s.*, t.canonical_name AS team FROM team_match_statistics s
                JOIN teams t ON t.id=s.team_id WHERE s.match_id=?
                ORDER BY s.period, s.stat_key, s.team_id""",
                (match_id,),
            )
        ]
    return {
        "match": match,
        "lineups": lineups,
        "referees": referees,
        "events": events,
        "team_statistics": statistics,
    }


@router.get("/teams/{team_id}/squad")
def team_squad(
    team_id: int,
    request: Request,
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
) -> list[dict]:
    if not repo.team(team_id, scope):
        raise HTTPException(status_code=404, detail="Team not found")
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            """SELECT s.*, p.canonical_name AS player, p.date_of_birth,
            p.primary_position FROM team_squads s JOIN players p ON p.id=s.player_id
            WHERE s.team_id=? AND s.active=1 ORDER BY s.shirt_number, p.canonical_name""",
            (team_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/players/{player_id}")
def player(player_id: int, request: Request, scope: Scope) -> dict:
    with request.app.state.database.connect(readonly=True) as conn:
        scope_values: list[int] = []
        squad_scope = ""
        stats_scope = ""
        if scope is not None:
            if not scope:
                raise HTTPException(status_code=404, detail="Player not found")
            placeholders = ",".join("?" for _ in scope)
            visible = conn.execute(
                f"""SELECT 1 FROM team_squads s JOIN matches m
                ON m.home_team_id=s.team_id OR m.away_team_id=s.team_id
                WHERE s.player_id=? AND m.competition_id IN ({placeholders}) LIMIT 1""",
                [player_id, *scope],
            ).fetchone()
            if not visible:
                raise HTTPException(status_code=404, detail="Player not found")
            scope_values = list(scope)
            squad_scope = f"""AND EXISTS (SELECT 1 FROM matches visible_match
            WHERE (visible_match.home_team_id=s.team_id OR visible_match.away_team_id=s.team_id)
            AND visible_match.competition_id IN ({placeholders}))"""
            stats_scope = f"AND m.competition_id IN ({placeholders})"
        row = conn.execute(
            """SELECT p.*, c.name AS country FROM players p
            LEFT JOIN countries c ON c.id=p.country_id WHERE p.id=?""",
            (player_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Player not found")
        squads = [
            dict(item)
            for item in conn.execute(
                f"""SELECT s.*, t.canonical_name AS team FROM team_squads s
                JOIN teams t ON t.id=s.team_id WHERE s.player_id=? {squad_scope}
                ORDER BY s.active DESC""",
                [player_id, *scope_values],
            )
        ]
        stats = [
            dict(item)
            for item in conn.execute(
                f"""SELECT ps.stat_key, count(*) AS matches, avg(ps.stat_value) AS average,
                sum(ps.stat_value) AS total FROM player_match_statistics ps
                JOIN matches m ON m.id=ps.match_id WHERE ps.player_id=? {stats_scope}
                GROUP BY stat_key ORDER BY stat_key""",
                [player_id, *scope_values],
            )
        ]
    result = dict(row)
    result["provider_payload"] = _json(result["provider_payload"])
    result.update({"squads": squads, "statistics": stats})
    return result


@router.get("/referees/{referee_id}")
def referee(referee_id: int, request: Request, scope: Scope) -> dict:
    clauses = ["r.id=?"]
    values: list[Any] = [referee_id]
    card_scope = ""
    card_values: list[Any] = [referee_id]
    if scope is not None:
        if not scope:
            raise HTTPException(status_code=404, detail="Referee not found")
        placeholders = ",".join("?" for _ in scope)
        clauses.append(f"m.competition_id IN ({placeholders})")
        values.extend(scope)
        card_scope = f"AND card_match.competition_id IN ({placeholders})"
        card_values.extend(scope)
    with request.app.state.database.connect(readonly=True) as conn:
        row = conn.execute(
            f"""SELECT r.*, c.name AS country, count(DISTINCT mr.match_id) AS matches
            FROM referees r LEFT JOIN countries c ON c.id=r.country_id
            LEFT JOIN match_referees mr ON mr.referee_id=r.id
            LEFT JOIN matches m ON m.id=mr.match_id WHERE {" AND ".join(clauses)}
            GROUP BY r.id""",
            values,
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Referee not found")
        cards = conn.execute(
            f"""SELECT e.event_type, count(*) AS total FROM match_events e
            JOIN match_referees mr ON mr.match_id=e.match_id
            JOIN matches card_match ON card_match.id=e.match_id
            WHERE mr.referee_id=? AND e.event_type IN ('YELLOW_CARD','RED_CARD')
            {card_scope} GROUP BY e.event_type""",
            card_values,
        ).fetchall()
    result = dict(row)
    result["provider_payload"] = _json(result["provider_payload"])
    result["discipline"] = {item["event_type"]: item["total"] for item in cards}
    return result


@router.put("/matches/{match_id}/lineups")
def save_lineup(
    match_id: int,
    body: LineupInput,
    request: Request,
    user: Analyst,
) -> dict:
    database = request.app.state.database
    with database.transaction() as conn:
        match = conn.execute(
            "SELECT home_team_id, away_team_id FROM matches WHERE id=?", (match_id,)
        ).fetchone()
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        if body.team_id not in {match["home_team_id"], match["away_team_id"]}:
            raise HTTPException(status_code=422, detail="Team does not participate in match")
        identifiers = [player.player_id for player in body.players]
        placeholders = ",".join("?" for _ in identifiers)
        found = conn.execute(
            f"SELECT count(*) FROM players WHERE id IN ({placeholders})", identifiers
        ).fetchone()[0]
        if found != len(identifiers):
            raise HTTPException(status_code=422, detail="Unknown player identifier")
        formation = None
        if body.formation_code:
            formation = conn.execute(
                "SELECT id FROM formations WHERE code=?", (body.formation_code,)
            ).fetchone()
            if not formation:
                raise HTTPException(status_code=422, detail="Unknown formation")
        lineup_id = conn.execute(
            """INSERT INTO lineups(match_id, team_id, status, formation_id, submitted_by,
            confidence, announced_at) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, team_id, status) DO UPDATE SET
            formation_id=excluded.formation_id, submitted_by=excluded.submitted_by,
            confidence=excluded.confidence, announced_at=excluded.announced_at,
            updated_at=CURRENT_TIMESTAMP RETURNING id""",
            (
                match_id,
                body.team_id,
                body.status,
                formation[0] if formation else None,
                user["id"],
                body.confidence,
                body.announced_at,
            ),
        ).fetchone()[0]
        conn.execute("DELETE FROM lineup_players WHERE lineup_id=?", (lineup_id,))
        conn.executemany(
            """INSERT INTO lineup_players(lineup_id, player_id, shirt_number, position_code,
            starter, field_x, field_y) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                (
                    lineup_id,
                    item.player_id,
                    item.shirt_number,
                    item.position_code,
                    int(item.starter),
                    item.field_x,
                    item.field_y,
                )
                for item in body.players
            ),
        )
        conn.execute(
            """INSERT INTO audit_log(actor_user_id, action, entity_type, entity_id,
            after_payload, remote_address) VALUES (?, 'UPSERT_LINEUP', 'lineups', ?, ?, ?)""",
            (
                user["id"],
                str(lineup_id),
                body.model_dump_json(),
                request.client.host if request.client else None,
            ),
        )
    return {"id": lineup_id, "match_id": match_id, **body.model_dump()}
