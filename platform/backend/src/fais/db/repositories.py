from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .connection import Database


@dataclass(slots=True)
class SportsRepository:
    database: Database

    @staticmethod
    def _scope(
        column: str, allowed_competition_ids: tuple[int, ...] | None
    ) -> tuple[str, list[int]]:
        if allowed_competition_ids is None:
            return "", []
        if not allowed_competition_ids:
            return "1=0", []
        placeholders = ",".join("?" for _ in allowed_competition_ids)
        return f"{column} IN ({placeholders})", list(allowed_competition_ids)

    def overview(self, allowed_competition_ids: tuple[int, ...] | None = None) -> dict[str, Any]:
        with self.database.connect(readonly=True) as conn:
            scope, values = self._scope("c.id", allowed_competition_ids)
            where = f"WHERE {scope}" if scope else ""
            if allowed_competition_ids is None:
                counts = {
                    name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                    for name in ("countries", "competitions", "teams", "matches", "predictions")
                }
            else:
                counts = {
                    "countries": conn.execute(
                        f"SELECT count(DISTINCT c.country_id) FROM competitions c {where}", values
                    ).fetchone()[0],
                    "competitions": conn.execute(
                        f"SELECT count(*) FROM competitions c {where}", values
                    ).fetchone()[0],
                    "teams": conn.execute(
                        f"""
                        SELECT count(DISTINCT team_id) FROM (
                            SELECT m.home_team_id AS team_id FROM matches m
                            JOIN competitions c ON c.id=m.competition_id {where}
                            UNION
                            SELECT m.away_team_id AS team_id FROM matches m
                            JOIN competitions c ON c.id=m.competition_id {where}
                        )
                        """,
                        [*values, *values],
                    ).fetchone()[0],
                    "matches": conn.execute(
                        f"""SELECT count(*) FROM matches m
                        JOIN competitions c ON c.id=m.competition_id {where}""",
                        values,
                    ).fetchone()[0],
                    "predictions": conn.execute(
                        f"""SELECT count(*) FROM predictions p
                        JOIN matches m ON m.id=p.match_id
                        JOIN competitions c ON c.id=m.competition_id {where}""",
                        values,
                    ).fetchone()[0],
                }
            match_scope, match_values = self._scope("competition_id", allowed_competition_ids)
            match_where = f"WHERE {match_scope}" if match_scope else ""
            status = {
                row[0]: row[1]
                for row in conn.execute(
                    f"""SELECT status, count(*) FROM matches {match_where}
                    GROUP BY status ORDER BY status""",
                    match_values,
                )
            }
            open_quality = (
                0
                if allowed_competition_ids is not None
                else conn.execute(
                    "SELECT count(*) FROM data_quality_issues WHERE resolved_at IS NULL"
                ).fetchone()[0]
            )
        return {"counts": counts, "matches_by_status": status, "open_quality_issues": open_quality}

    def competitions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        allowed_competition_ids: tuple[int, ...] | None = None,
    ) -> list[dict[str, Any]]:
        scope, values = self._scope("c.id", allowed_competition_ids)
        where = f"WHERE {scope}" if scope else ""
        values.extend((min(max(limit, 1), 500), max(offset, 0)))
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                f"""
                SELECT c.id, c.slug, c.name, c.sport, c.active,
                       co.name AS country, count(m.id) AS match_count
                FROM competitions c
                LEFT JOIN countries co ON co.id=c.country_id
                LEFT JOIN matches m ON m.competition_id=c.id
                {where}
                GROUP BY c.id
                ORDER BY co.name, c.name
                LIMIT ? OFFSET ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def matches(
        self,
        *,
        competition_id: int | None = None,
        team_id: int | None = None,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
        allowed_competition_ids: tuple[int, ...] | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        scope, scope_values = self._scope("m.competition_id", allowed_competition_ids)
        if scope:
            clauses.append(scope)
            values.extend(scope_values)
        if competition_id is not None:
            clauses.append("m.competition_id=?")
            values.append(competition_id)
        if status is not None:
            clauses.append("m.status=?")
            values.append(status.upper())
        if team_id is not None:
            clauses.append("(m.home_team_id=? OR m.away_team_id=?)")
            values.extend((team_id, team_id))
        if from_date is not None:
            clauses.append("m.kickoff_date>=?")
            values.append(from_date)
        if to_date is not None:
            clauses.append("m.kickoff_date<=?")
            values.append(to_date)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        values.extend((min(max(limit, 1), 500), max(offset, 0)))
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                f"""
                SELECT m.id, m.competition_id, c.name AS competition,
                       ht.canonical_name AS home_team, at.canonical_name AS away_team,
                       m.kickoff_utc, m.kickoff_date, m.kickoff_precision,
                       m.kickoff_raw, m.round_name, m.status,
                       m.home_score, m.away_score
                FROM matches m
                JOIN competitions c ON c.id=m.competition_id
                JOIN teams ht ON ht.id=m.home_team_id
                JOIN teams at ON at.id=m.away_team_id
                {where}
                ORDER BY COALESCE(m.kickoff_utc, m.kickoff_date, '9999'), m.id
                LIMIT ? OFFSET ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def teams(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
        allowed_competition_ids: tuple[int, ...] | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if search:
            clauses.append("t.normalized_name LIKE ?")
            values.append(f"%{search.casefold()}%")
        scope, scope_values = self._scope("m.competition_id", allowed_competition_ids)
        if scope:
            clauses.append(scope)
            values.extend(scope_values)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        values.extend((min(max(limit, 1), 500), max(offset, 0)))
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                f"""
                SELECT t.id, t.canonical_name AS name, co.name AS country,
                       count(m.id) AS match_count
                FROM teams t
                LEFT JOIN countries co ON co.id=t.country_id
                LEFT JOIN matches m ON m.home_team_id=t.id OR m.away_team_id=t.id
                {where}
                GROUP BY t.id
                ORDER BY match_count DESC, t.canonical_name
                LIMIT ? OFFSET ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def team(
        self, team_id: int, allowed_competition_ids: tuple[int, ...] | None = None
    ) -> dict[str, Any] | None:
        scope, values = self._scope("m.competition_id", allowed_competition_ids)
        with self.database.connect(readonly=True) as conn:
            if scope:
                allowed = conn.execute(
                    f"""SELECT 1 FROM matches m WHERE (m.home_team_id=? OR m.away_team_id=?)
                    AND {scope} LIMIT 1""",
                    [team_id, team_id, *values],
                ).fetchone()
                if not allowed:
                    return None
            team = conn.execute(
                """
                SELECT t.id, t.canonical_name AS name, co.name AS country
                FROM teams t LEFT JOIN countries co ON co.id=t.country_id WHERE t.id=?
                """,
                (team_id,),
            ).fetchone()
            if not team:
                return None
            match_scope, match_values = self._scope("competition_id", allowed_competition_ids)
            scope_sql = f"AND {match_scope}" if match_scope else ""
            rows = conn.execute(
                f"""
                SELECT id, home_team_id, away_team_id, home_score, away_score, kickoff_date
                FROM matches
                WHERE status='FINISHED' AND (home_team_id=? OR away_team_id=?)
                  AND home_score IS NOT NULL
                  {scope_sql}
                ORDER BY COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z') DESC, id DESC
                """,
                [team_id, team_id, *match_values],
            ).fetchall()
        wins = draws = losses = goals_for = goals_against = 0
        form: list[str] = []
        for row in rows:
            home = row["home_team_id"] == team_id
            scored = row["home_score"] if home else row["away_score"]
            conceded = row["away_score"] if home else row["home_score"]
            goals_for += scored
            goals_against += conceded
            result = "W" if scored > conceded else "D" if scored == conceded else "L"
            wins += int(result == "W")
            draws += int(result == "D")
            losses += int(result == "L")
            if len(form) < 5:
                form.append(result)
        return {
            **dict(team),
            "played": len(rows),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "form": form,
        }

    def match(
        self, match_id: int, allowed_competition_ids: tuple[int, ...] | None = None
    ) -> dict[str, Any] | None:
        scope, values = self._scope("m.competition_id", allowed_competition_ids)
        scope_sql = f"AND {scope}" if scope else ""
        with self.database.connect(readonly=True) as conn:
            row = conn.execute(
                f"""
                SELECT m.*, c.name AS competition,
                       ht.canonical_name AS home_team, at.canonical_name AS away_team
                FROM matches m
                JOIN competitions c ON c.id=m.competition_id
                JOIN teams ht ON ht.id=m.home_team_id
                JOIN teams at ON at.id=m.away_team_id
                WHERE m.id=? {scope_sql}
                """,
                [match_id, *values],
            ).fetchone()
        return dict(row) if row else None

    def latest_prediction(self, match_id: int) -> dict[str, Any] | None:
        with self.database.connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, match_id, cutoff_utc, model_version, feature_version, status,
                       home_lambda, away_lambda, payload, created_at
                FROM predictions WHERE match_id=? ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (match_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def quality_issues(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, entity_type, entity_id, code, severity, context,
                       detected_at, resolved_at
                FROM data_quality_issues
                ORDER BY resolved_at IS NULL DESC, detected_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (min(max(limit, 1), 500), max(offset, 0)),
            ).fetchall()
        results = [dict(row) for row in rows]
        for result in results:
            result["context"] = json.loads(result["context"]) if result["context"] else None
        return results

    def models(self) -> list[dict[str, Any]]:
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, name, algorithm, version, feature_version, training_cutoff_utc,
                       metrics, active, created_at
                FROM model_versions ORDER BY name, created_at DESC
                """
            ).fetchall()
        results = [dict(row) for row in rows]
        for result in results:
            result["metrics"] = json.loads(result["metrics"])
            result["active"] = bool(result["active"])
        return results

    def backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT b.id, mv.name AS model, mv.version, b.started_at, b.finished_at,
                       b.cutoff_start_utc, b.cutoff_end_utc, b.metrics, b.status, b.error
                FROM backtest_runs b JOIN model_versions mv ON mv.id=b.model_version_id
                ORDER BY b.started_at DESC LIMIT ?
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        results = [dict(row) for row in rows]
        for result in results:
            result["metrics"] = json.loads(result["metrics"]) if result["metrics"] else None
        return results
