from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class TeamFeatures:
    team_id: int
    cutoff_utc: str
    sample_size: int
    goals_for_per_match: float
    goals_against_per_match: float
    home_goals_for_per_match: float
    away_goals_for_per_match: float
    league_goals_per_team_match: float

    def payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FeaturePair:
    home: TeamFeatures
    away: TeamFeatures
    input_hash: str


class FeatureBuilder:
    version = "team-goals-v1"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def for_match(self, match_id: int) -> FeaturePair:
        target = self.conn.execute(
            """
            SELECT id, competition_id, home_team_id, away_team_id,
                   kickoff_utc, kickoff_date
            FROM matches WHERE id=?
            """,
            (match_id,),
        ).fetchone()
        if not target:
            raise ValueError(f"Match {match_id} does not exist")
        cutoff = target["kickoff_utc"] or (
            f"{target['kickoff_date']}T00:00:00Z" if target["kickoff_date"] else None
        )
        if not cutoff:
            raise ValueError(
                f"Match {match_id} has no unambiguous kickoff; temporal features are blocked"
            )
        historical = self.conn.execute(
            """
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM matches
            WHERE competition_id=? AND status='FINISHED'
              AND COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z') < ?
              AND home_score IS NOT NULL AND away_score IS NOT NULL
            ORDER BY COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z'), id
            """,
            (target["competition_id"], cutoff),
        ).fetchall()
        if not historical:
            league_rate = 1.30
        else:
            league_rate = sum(r["home_score"] + r["away_score"] for r in historical) / (
                2 * len(historical)
            )
        home = self._team(target["home_team_id"], cutoff, historical, league_rate)
        away = self._team(target["away_team_id"], cutoff, historical, league_rate)
        encoded = json.dumps(
            {"version": self.version, "home": home.payload(), "away": away.payload()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return FeaturePair(home=home, away=away, input_hash=hashlib.sha256(encoded).hexdigest())

    @staticmethod
    def _team(team_id: int, cutoff: str, rows, league_rate: float) -> TeamFeatures:
        gf: list[int] = []
        ga: list[int] = []
        home_gf: list[int] = []
        away_gf: list[int] = []
        for row in rows:
            if row["home_team_id"] == team_id:
                gf.append(row["home_score"])
                ga.append(row["away_score"])
                home_gf.append(row["home_score"])
            elif row["away_team_id"] == team_id:
                gf.append(row["away_score"])
                ga.append(row["home_score"])
                away_gf.append(row["away_score"])

        def shrink(values: list[int], prior: float, weight: float = 8.0) -> float:
            return (sum(values) + prior * weight) / (len(values) + weight)

        return TeamFeatures(
            team_id=team_id,
            cutoff_utc=cutoff,
            sample_size=len(gf),
            goals_for_per_match=round(shrink(gf, league_rate), 6),
            goals_against_per_match=round(shrink(ga, league_rate), 6),
            home_goals_for_per_match=round(shrink(home_gf, league_rate * 1.08), 6),
            away_goals_for_per_match=round(shrink(away_gf, league_rate * 0.92), 6),
            league_goals_per_team_match=round(league_rate, 6),
        )
