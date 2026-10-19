from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fais.db import Database

from .legacy_sqlite import canonical_status, normalize_name
from .seasons import assign_dataset_seasons
from .temporal import parse_kickoff


@dataclass(slots=True)
class JsonIngestionSummary:
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    rejected: int = 0


class JsonMatchFeed:
    """Adapter for the JSON files produced by the existing Flashscore scrapers."""

    def __init__(self, database: Database):
        self.database = database

    def run(
        self,
        path: str | Path,
        *,
        country_slug: str,
        competition_slug: str,
        captured_on: date,
        source_timezone: str = "America/Bogota",
    ) -> JsonIngestionSummary:
        records = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(records, list):
            raise ValueError("The match feed must be a JSON array")
        summary = JsonIngestionSummary(seen=len(records))
        with self.database.transaction() as conn:
            provider_id = conn.execute(
                "SELECT id FROM source_providers WHERE code='flashscore_live'"
            ).fetchone()[0]
            competition = conn.execute(
                """
                SELECT c.id, c.country_id FROM competitions c
                JOIN countries co ON co.id=c.country_id
                WHERE co.slug=? AND c.slug=?
                """,
                (country_slug, competition_slug),
            ).fetchone()
            if not competition:
                raise ValueError(f"Unknown competition: {country_slug}/{competition_slug}")
            run_id = conn.execute(
                """
                INSERT INTO ingestion_runs(
                    provider_id, job_type, status, started_at, metadata
                ) VALUES (?, 'JSON_MATCH_FEED', 'RUNNING', CURRENT_TIMESTAMP, ?)
                RETURNING id
                """,
                (provider_id, json.dumps({"path": str(path)})),
            ).fetchone()[0]
        try:
            with self.database.transaction() as conn:
                for record in records:
                    if self._upsert(
                        conn,
                        provider_id,
                        competition[0],
                        competition[1],
                        record,
                        captured_on,
                        source_timezone,
                    ):
                        summary.inserted += 1
                    else:
                        summary.updated += 1
                assign_dataset_seasons(conn)
                conn.execute(
                    """
                    UPDATE ingestion_runs SET status='SUCCEEDED', finished_at=CURRENT_TIMESTAMP,
                        records_seen=?, records_written=? WHERE id=?
                    """,
                    (summary.seen, summary.inserted + summary.updated, run_id),
                )
        except Exception as error:
            with self.database.transaction() as conn:
                conn.execute(
                    """
                    UPDATE ingestion_runs SET status='FAILED', finished_at=CURRENT_TIMESTAMP,
                        records_seen=?, records_written=?, error=? WHERE id=?
                    """,
                    (summary.seen, summary.inserted + summary.updated, str(error)[:4000], run_id),
                )
            raise
        return summary

    @staticmethod
    def _team(conn, provider_id: int, country_id: int, name: str) -> int:
        clean = name.removesuffix("GOL").strip()
        normalized = normalize_name(clean)
        conn.execute(
            """
            INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?)
            ON CONFLICT(country_id, normalized_name) DO NOTHING
            """,
            (clean, normalized, country_id),
        )
        team_id = conn.execute(
            "SELECT id FROM teams WHERE country_id=? AND normalized_name=?",
            (country_id, normalized),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO team_aliases(team_id, provider_id, country_id, alias, normalized_alias)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider_id, country_id, normalized_alias)
            DO UPDATE SET team_id=excluded.team_id, alias=excluded.alias
            """,
            (team_id, provider_id, country_id, name, normalize_name(name)),
        )
        return team_id

    def _upsert(
        self,
        conn,
        provider_id: int,
        competition_id: int,
        country_id: int,
        record: dict[str, Any],
        captured_on: date,
        source_timezone: str,
    ) -> bool:
        required = ("id", "equipo_local", "equipo_visitante")
        if any(not record.get(key) for key in required):
            raise ValueError(f"Invalid match record; required fields: {', '.join(required)}")
        external_id = str(record["id"])
        current = conn.execute(
            "SELECT match_id FROM match_provider_refs WHERE provider_id=? AND external_id=?",
            (provider_id, external_id),
        ).fetchone()
        kickoff = parse_kickoff(
            record.get("fecha_hora"),
            reference_date=captured_on,
            source_timezone=source_timezone,
        )
        home_score = record.get("goles_local")
        away_score = record.get("goles_visitante")
        if (home_score is None) != (away_score is None):
            home_score = away_score = None
        values = (
            competition_id,
            self._team(conn, provider_id, country_id, record["equipo_local"]),
            self._team(conn, provider_id, country_id, record["equipo_visitante"]),
            kickoff.utc,
            kickoff.local_date,
            record.get("fecha_hora"),
            kickoff.timezone,
            kickoff.precision,
            int(kickoff.year_inferred),
            record.get("jornada"),
            canonical_status(record.get("tipo", "proximo"), record.get("estado")),
            "RESULT" if record.get("tipo") == "resultado" else "UPCOMING",
            home_score,
            away_score,
        )
        if current:
            match_id = current[0]
            conn.execute(
                """
                UPDATE matches SET competition_id=?, home_team_id=?, away_team_id=?,
                    kickoff_utc=?, kickoff_date=?, kickoff_raw=?, kickoff_timezone=?,
                    kickoff_precision=?, kickoff_year_inferred=?, round_name=?, status=?,
                    match_type=?, home_score=?, away_score=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (*values, match_id),
            )
            inserted = False
        else:
            conn.execute(
                """
                INSERT INTO matches(
                    competition_id, home_team_id, away_team_id, kickoff_utc, kickoff_date,
                    kickoff_raw, kickoff_timezone, kickoff_precision, kickoff_year_inferred,
                    round_name, status, match_type, home_score, away_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            match_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            inserted = True
        raw_hash = hashlib.sha256(
            json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO match_provider_refs(
                match_id, provider_id, external_id, url, raw_hash, fetched_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(provider_id, external_id) DO UPDATE SET
                match_id=excluded.match_id, url=excluded.url, raw_hash=excluded.raw_hash,
                fetched_at=excluded.fetched_at
            """,
            (match_id, provider_id, external_id, record.get("link"), raw_hash),
        )
        return inserted
