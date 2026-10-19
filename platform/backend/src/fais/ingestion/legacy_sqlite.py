from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from fais.db.connection import Database

from .seasons import assign_dataset_seasons
from .temporal import parse_kickoff


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def slugify(value: str) -> str:
    return normalize_name(value).replace(" ", "-") or "unknown"


def canonical_status(match_type: str, legacy_status: str | None) -> str:
    status = (legacy_status or "").casefold()
    if match_type == "resultado":
        return "SUSPENDED" if "suspend" in status else "FINISHED"
    if "aplaz" in status or "postpon" in status:
        return "POSTPONED"
    if "cancel" in status:
        return "CANCELLED"
    return "SCHEDULED"


@dataclass(slots=True)
class ImportSummary:
    countries: int = 0
    competitions: int = 0
    teams: int = 0
    matches: int = 0
    quality_issues: int = 0
    kickoffs_minute: int = 0
    kickoffs_date_only: int = 0
    kickoffs_unknown: int = 0
    years_inferred: int = 0
    seasons: int = 0


class LegacyImporter:
    def __init__(
        self,
        target: Database,
        *,
        reference_date: date | None = None,
        source_timezone: str = "America/Bogota",
    ):
        self.target = target
        self.reference_date = reference_date
        self.source_timezone = source_timezone

    def run(self, legacy_path: str | Path) -> ImportSummary:
        legacy_uri = f"file:{Path(legacy_path).resolve()}?mode=ro&immutable=1"
        source = sqlite3.connect(legacy_uri, uri=True)
        source.row_factory = sqlite3.Row
        summary = ImportSummary()
        try:
            reference_date = self.reference_date or self._source_reference_date(source)
            with self.target.transaction() as target:
                provider_id = target.execute(
                    "SELECT id FROM source_providers WHERE code='legacy_flashscore'"
                ).fetchone()[0]
                country_map = self._countries(source, target, summary)
                competition_map = self._competitions(
                    source, target, provider_id, country_map, summary
                )
                team_map = self._teams(source, target, provider_id, summary)
                self._matches(
                    source,
                    target,
                    provider_id,
                    competition_map,
                    team_map,
                    summary,
                    reference_date,
                    self.source_timezone,
                )
                summary.seasons = assign_dataset_seasons(target)
        finally:
            source.close()
        return summary

    @staticmethod
    def _source_reference_date(source: sqlite3.Connection) -> date | None:
        table = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkpoints_competiciones'"
        ).fetchone()
        if not table:
            return None
        row = source.execute(
            "SELECT max(fecha_actualizacion) FROM checkpoints_competiciones"
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return datetime.fromisoformat(row[0]).date()
        except ValueError:
            return None

    @staticmethod
    def _countries(source, target, summary: ImportSummary) -> dict[int, int]:
        mapping: dict[int, int] = {}
        for row in source.execute("SELECT * FROM paises ORDER BY id"):
            target.execute(
                """
                INSERT INTO countries(id, slug, name, provider_payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, name=excluded.name,
                    provider_payload=excluded.provider_payload
                """,
                (row["id"], row["slug"], row["nombre_flashscore"], json.dumps(dict(row))),
            )
            mapping[row["id"]] = row["id"]
            summary.countries += 1
        return mapping

    @staticmethod
    def _competitions(
        source, target, provider_id, country_map, summary
    ) -> dict[int, tuple[int, int]]:
        mapping: dict[int, tuple[int, int]] = {}
        for row in source.execute("SELECT * FROM competiciones ORDER BY id"):
            competition_id = row["id"]
            target.execute(
                """
                INSERT INTO competitions(id, country_id, slug, name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET country_id=excluded.country_id,
                    slug=excluded.slug, name=excluded.name
                """,
                (
                    competition_id,
                    country_map.get(row["pais_id"]),
                    slugify(row["nombre_flashscore"]),
                    row["nombre_flashscore"],
                ),
            )
            target.execute(
                """
                INSERT INTO competition_provider_refs(
                    competition_id, provider_id, external_id, external_name, url
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, external_id) DO UPDATE SET
                    competition_id=excluded.competition_id,
                    external_name=excluded.external_name, url=excluded.url
                """,
                (
                    competition_id,
                    provider_id,
                    str(competition_id),
                    row["nombre_flashscore"],
                    row["link_flashscore"],
                ),
            )
            mapping[competition_id] = (competition_id, row["pais_id"])
            summary.competitions += 1
        return mapping

    @staticmethod
    def _teams(source, target, provider_id, summary) -> dict[tuple[int, str], int]:
        names = {
            (int(row[0]), str(row[1]).strip())
            for row in source.execute(
                """
                SELECT c.pais_id, p.equipo_local
                FROM partidos p JOIN competiciones c ON c.id=p.competicion_id
                UNION
                SELECT c.pais_id, p.equipo_visitante
                FROM partidos p JOIN competiciones c ON c.id=p.competicion_id
                """
            )
            if row[1] and str(row[1]).strip()
        }
        mapping: dict[tuple[int, str], int] = {}
        for country_id, name in sorted(names, key=lambda item: (item[0], normalize_name(item[1]))):
            normalized = normalize_name(name.removesuffix("GOL").strip())
            target.execute(
                "INSERT INTO teams(canonical_name, normalized_name, country_id) VALUES (?, ?, ?) "
                "ON CONFLICT(country_id, normalized_name) DO NOTHING",
                (name.removesuffix("GOL").strip(), normalized, country_id),
            )
            team_id = target.execute(
                "SELECT id FROM teams WHERE country_id=? AND normalized_name=?",
                (country_id, normalized),
            ).fetchone()[0]
            target.execute(
                """
                INSERT INTO team_aliases(
                    team_id, provider_id, country_id, alias, normalized_alias
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, country_id, normalized_alias)
                DO UPDATE SET team_id=excluded.team_id
                """,
                (team_id, provider_id, country_id, name, normalize_name(name)),
            )
            mapping[(country_id, name)] = team_id
        summary.teams = len({*mapping.values()})
        return mapping

    @staticmethod
    def _matches(
        source,
        target,
        provider_id,
        competition_map,
        team_map,
        summary,
        reference_date,
        source_timezone,
    ) -> None:
        for row in source.execute("SELECT * FROM partidos ORDER BY rowid"):
            external_id = str(row["id"])
            existing = target.execute(
                "SELECT match_id FROM match_provider_refs WHERE provider_id=? AND external_id=?",
                (provider_id, external_id),
            ).fetchone()
            raw_date = row["fecha_hora"]
            kickoff = parse_kickoff(
                raw_date, reference_date=reference_date, source_timezone=source_timezone
            )
            home_score = row["goles_local"]
            away_score = row["goles_visitante"]
            if (home_score is None) != (away_score is None):
                home_score = away_score = None
            competition_id, country_id = competition_map[row["competicion_id"]]
            values = (
                competition_id,
                team_map[(country_id, row["equipo_local"])],
                team_map[(country_id, row["equipo_visitante"])],
                kickoff.utc,
                raw_date,
                row["jornada"],
                canonical_status(row["tipo"], row["estado"]),
                "RESULT" if row["tipo"] == "resultado" else "UPCOMING",
                home_score,
                away_score,
                kickoff.local_date,
                kickoff.timezone,
                kickoff.precision,
                int(kickoff.year_inferred),
            )
            if existing:
                match_id = existing[0]
                target.execute(
                    """
                    UPDATE matches SET competition_id=?, home_team_id=?, away_team_id=?,
                        kickoff_utc=?, kickoff_raw=?, round_name=?, status=?, match_type=?,
                        home_score=?, away_score=?, kickoff_date=?, kickoff_timezone=?,
                        kickoff_precision=?, kickoff_year_inferred=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (*values, match_id),
                )
            else:
                target.execute(
                    """
                    INSERT INTO matches(
                        competition_id, home_team_id, away_team_id, kickoff_utc, kickoff_raw,
                        round_name, status, match_type, home_score, away_score, kickoff_date,
                        kickoff_timezone, kickoff_precision, kickoff_year_inferred
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                match_id = target.execute("SELECT last_insert_rowid()").fetchone()[0]
            raw_hash = hashlib.sha256(
                json.dumps(dict(row), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            target.execute(
                """
                INSERT INTO match_provider_refs(match_id, provider_id, external_id, url, raw_hash)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, external_id) DO UPDATE SET
                    match_id=excluded.match_id, url=excluded.url, raw_hash=excluded.raw_hash
                """,
                (match_id, provider_id, external_id, row["link"], raw_hash),
            )
            if kickoff.precision == "MINUTE":
                summary.kickoffs_minute += 1
            elif kickoff.precision == "DATE":
                summary.kickoffs_date_only += 1
            else:
                summary.kickoffs_unknown += 1
            summary.years_inferred += int(kickoff.year_inferred)

            issue_code = None
            issue_message = None
            if kickoff.precision == "UNKNOWN":
                issue_code = "AMBIGUOUS_KICKOFF"
                issue_message = "Legacy kickoff could not be converted safely"
            elif kickoff.precision == "DATE":
                issue_code = "MISSING_KICKOFF_TIME"
                issue_message = "Legacy kickoff has date precision but no start time"
            if issue_code:
                target.execute(
                    """
                    INSERT INTO data_quality_issues(
                        entity_type, entity_id, source_provider_id, severity, code, message, context
                    ) VALUES ('match', ?, ?, 'WARNING', ?, ?, ?)
                    ON CONFLICT(entity_type, entity_id, source_provider_id, code)
                    DO UPDATE SET severity=excluded.severity, message=excluded.message,
                                  context=excluded.context, detected_at=CURRENT_TIMESTAMP,
                                  resolved_at=NULL
                    """,
                    (
                        str(match_id),
                        provider_id,
                        issue_code,
                        issue_message,
                        json.dumps(
                            {
                                "raw": raw_date,
                                "reference_date": reference_date.isoformat()
                                if reference_date
                                else None,
                                "timezone": source_timezone,
                                "suffix": kickoff.suffix,
                            }
                        ),
                    ),
                )
                summary.quality_issues += 1
            if kickoff.precision != "UNKNOWN":
                target.execute(
                    """
                    UPDATE data_quality_issues SET resolved_at=CURRENT_TIMESTAMP
                    WHERE entity_type='match' AND entity_id=? AND source_provider_id=?
                      AND code='AMBIGUOUS_KICKOFF' AND resolved_at IS NULL
                    """,
                    (str(match_id), provider_id),
                )
            if kickoff.precision == "MINUTE":
                target.execute(
                    """
                    UPDATE data_quality_issues SET resolved_at=CURRENT_TIMESTAMP
                    WHERE entity_type='match' AND entity_id=? AND source_provider_id=?
                      AND code='MISSING_KICKOFF_TIME' AND resolved_at IS NULL
                    """,
                    (str(match_id), provider_id),
                )
            summary.matches += 1
