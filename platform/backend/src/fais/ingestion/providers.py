from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from fais.db import Database

from .json_feed import JsonMatchFeed
from .legacy_sqlite import normalize_name

PROVIDER_CODES = {"flashscore": "flashscore_live", "fotmob": "fotmob", "betplay": "betplay"}


class ControlledProviderIngester:
    """Ingest provider snapshots from the configured inbox without executing arbitrary code."""

    def __init__(self, database: Database, inbox_root: str | Path):
        self.database = database
        self.inbox_root = Path(inbox_root).resolve()

    def _safe_path(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        if resolved != self.inbox_root and self.inbox_root not in resolved.parents:
            raise ValueError("Provider files must be staged inside FAIS_INBOX_PATH")
        if resolved.suffix.casefold() != ".json" or not resolved.is_file():
            raise ValueError("Provider input must be an existing JSON file")
        return resolved

    def run(
        self,
        path: str | Path,
        *,
        provider_code: str,
        ingestion_kind: str,
        country_slug: str,
        competition_slug: str,
        captured_on: date,
    ) -> dict[str, Any]:
        staged = self._safe_path(path)
        provider_code = provider_code.casefold()
        ingestion_kind = ingestion_kind.upper()
        if provider_code not in PROVIDER_CODES:
            raise ValueError("Unsupported provider")
        with self.database.connect(readonly=True) as conn:
            source = conn.execute(
                """SELECT 1 FROM scraper_sources WHERE provider_code=? AND ingestion_kind=?
                AND country_slug=? AND competition_slug=? AND enabled=1""",
                (provider_code, ingestion_kind, country_slug, competition_slug),
            ).fetchone()
        if not source:
            raise ValueError("Provider source is not enabled for this competition")
        if ingestion_kind == "MATCHES":
            if provider_code != "flashscore":
                raise ValueError("MATCHES snapshots currently require the Flashscore adapter")
            return asdict(
                JsonMatchFeed(self.database).run(
                    staged,
                    country_slug=country_slug,
                    competition_slug=competition_slug,
                    captured_on=captured_on,
                )
            )
        payload = json.loads(staged.read_text(encoding="utf-8-sig"))
        if ingestion_kind == "ODDS":
            return self._odds(payload, provider_code)
        if ingestion_kind == "DETAILS":
            return self._details(payload, provider_code)
        raise ValueError("Unsupported ingestion kind")

    def _provider(self, conn, provider_code: str) -> int:
        code = PROVIDER_CODES[provider_code]
        row = conn.execute("SELECT id FROM source_providers WHERE code=?", (code,)).fetchone()
        if not row:
            raise ValueError(f"Source provider is not registered: {code}")
        return row[0]

    @staticmethod
    def _match_id(conn, provider_id: int, record: dict[str, Any]) -> int:
        if record.get("match_id"):
            match_id = int(record["match_id"])
            if conn.execute("SELECT 1 FROM matches WHERE id=?", (match_id,)).fetchone():
                return match_id
        external = record.get("external_match_id")
        row = conn.execute(
            "SELECT match_id FROM match_provider_refs WHERE provider_id=? AND external_id=?",
            (provider_id, str(external)),
        ).fetchone()
        if not row:
            raise ValueError("Unknown match reference")
        return row[0]

    def _odds(self, payload: Any, provider_code: str) -> dict[str, int]:
        records = payload.get("odds", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Odds feed must be a list or contain an odds list")
        written = 0
        with self.database.transaction() as conn:
            provider_id = self._provider(conn, provider_code)
            for record in records:
                match_id = self._match_id(conn, provider_id, record)
                odd = float(record["decimal_odd"])
                if odd <= 1:
                    raise ValueError("decimal_odd must be greater than 1")
                market = str(record["market_key"]).upper()
                selection = str(record["selection_key"]).upper()
                line = record.get("line")
                captured_at = str(record["captured_at"])
                raw = json.dumps(record, separators=(",", ":"))
                existing = conn.execute(
                    """SELECT id FROM odds_snapshots WHERE match_id=? AND provider_id=?
                    AND market_key=? AND selection_key=? AND line IS ? AND captured_at=?""",
                    (match_id, provider_id, market, selection, line, captured_at),
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE odds_snapshots SET decimal_odd=?, raw_payload=?
                        WHERE id=?""",
                        (odd, raw, existing[0]),
                    )
                else:
                    conn.execute(
                        """INSERT INTO odds_snapshots(
                        match_id, provider_id, market_key, selection_key, line,
                        decimal_odd, captured_at, raw_payload
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            match_id,
                            provider_id,
                            market,
                            selection,
                            line,
                            odd,
                            captured_at,
                            raw,
                        ),
                    )
                written += 1
        return {"seen": len(records), "written": written}

    def _player(self, conn, provider_id: int, record: dict[str, Any]) -> int:
        external_id = str(record["external_id"])
        current = conn.execute(
            "SELECT player_id FROM player_provider_refs WHERE provider_id=? AND external_id=?",
            (provider_id, external_id),
        ).fetchone()
        if current:
            player_id = current[0]
            conn.execute(
                """UPDATE players SET canonical_name=?, normalized_name=?,
                primary_position=?, provider_payload=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (
                    record["name"].strip(),
                    normalize_name(record["name"]),
                    record.get("position"),
                    json.dumps(record, separators=(",", ":")),
                    player_id,
                ),
            )
            return player_id
        row = conn.execute(
            """INSERT INTO players(canonical_name, normalized_name, country_id, date_of_birth,
               primary_position, provider_payload) VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                record["name"].strip(),
                normalize_name(record["name"]),
                record.get("country_id"),
                record.get("date_of_birth"),
                record.get("position"),
                json.dumps(record, separators=(",", ":")),
            ),
        ).fetchone()
        player_id = row[0]
        conn.execute(
            """INSERT INTO player_provider_refs(player_id, provider_id, external_id, external_name)
            VALUES (?, ?, ?, ?)""",
            (player_id, provider_id, external_id, record["name"]),
        )
        return player_id

    @staticmethod
    def _squad(conn, player_id: int, record: dict[str, Any]) -> bool:
        if record.get("team_id") is None:
            return False
        team_id = int(record["team_id"])
        season_id = record.get("season_id")
        existing = conn.execute(
            """SELECT id FROM team_squads WHERE team_id=? AND season_id IS ?
            AND player_id=?""",
            (team_id, season_id, player_id),
        ).fetchone()
        values = (
            record.get("shirt_number"),
            record.get("position"),
            int(record.get("active", True)),
            record.get("starts_at"),
            record.get("ends_at"),
        )
        if existing:
            conn.execute(
                """UPDATE team_squads SET shirt_number=?, position=?, active=?,
                starts_at=?, ends_at=? WHERE id=?""",
                (*values, existing[0]),
            )
        else:
            conn.execute(
                """INSERT INTO team_squads(team_id, season_id, player_id, shirt_number,
                position, active, starts_at, ends_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (team_id, season_id, player_id, *values),
            )
        return True

    def _details(self, payload: Any, provider_code: str) -> dict[str, int]:
        if not isinstance(payload, dict):
            raise ValueError("Details feed must be a JSON object")
        counts = {
            "players": 0,
            "squads": 0,
            "referees": 0,
            "lineups": 0,
            "events": 0,
            "statistics": 0,
            "player_statistics": 0,
        }
        with self.database.transaction() as conn:
            provider_id = self._provider(conn, provider_code)
            match_id = self._match_id(conn, provider_id, payload)
            match = conn.execute(
                "SELECT home_team_id, away_team_id FROM matches WHERE id=?", (match_id,)
            ).fetchone()
            match_teams = {match["home_team_id"], match["away_team_id"]}
            players: dict[str, int] = {}
            for record in payload.get("players", []):
                if record.get("team_id") is not None and record["team_id"] not in match_teams:
                    raise ValueError("Player squad team does not participate in match")
                players[str(record["external_id"])] = self._player(conn, provider_id, record)
                if self._squad(conn, players[str(record["external_id"])], record):
                    counts["squads"] += 1
                counts["players"] += 1
            for record in payload.get("referees", []):
                external_id = str(record["external_id"])
                existing = conn.execute(
                    """SELECT referee_id FROM referee_provider_refs
                    WHERE provider_id=? AND external_id=?""",
                    (provider_id, external_id),
                ).fetchone()
                if existing:
                    referee_id = existing[0]
                    conn.execute(
                        """UPDATE referees SET canonical_name=?, normalized_name=?,
                        category=?, provider_payload=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (
                            record["name"],
                            normalize_name(record["name"]),
                            record.get("category"),
                            json.dumps(record, separators=(",", ":")),
                            referee_id,
                        ),
                    )
                else:
                    referee_id = conn.execute(
                        """INSERT INTO referees(
                        canonical_name, normalized_name, country_id, category,
                        provider_payload) VALUES (?, ?, ?, ?, ?) RETURNING id""",
                        (
                            record["name"],
                            normalize_name(record["name"]),
                            record.get("country_id"),
                            record.get("category"),
                            json.dumps(record, separators=(",", ":")),
                        ),
                    ).fetchone()[0]
                    conn.execute(
                        "INSERT INTO referee_provider_refs VALUES (?, ?, ?, ?)",
                        (referee_id, provider_id, external_id, record["name"]),
                    )
                conn.execute(
                    """INSERT OR REPLACE INTO match_referees(match_id, referee_id, role)
                    VALUES (?, ?, ?)""",
                    (match_id, referee_id, record.get("role", "MAIN").upper()),
                )
                counts["referees"] += 1
            for record in payload.get("lineups", []):
                if record["team_id"] not in match_teams:
                    raise ValueError("Lineup team does not participate in match")
                formation = conn.execute(
                    "SELECT id FROM formations WHERE code=?", (record.get("formation"),)
                ).fetchone()
                lineup_id = conn.execute(
                    """INSERT INTO lineups(match_id, team_id, status, formation_id,
                       source_provider_id, confidence, announced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(match_id, team_id, status)
                       DO UPDATE SET formation_id=excluded.formation_id,
                       source_provider_id=excluded.source_provider_id,
                       confidence=excluded.confidence,
                       announced_at=excluded.announced_at, updated_at=CURRENT_TIMESTAMP
                       RETURNING id""",
                    (
                        match_id,
                        record["team_id"],
                        record.get("status", "CONFIRMED").upper(),
                        formation[0] if formation else None,
                        provider_id,
                        record.get("confidence"),
                        record.get("announced_at"),
                    ),
                ).fetchone()[0]
                conn.execute("DELETE FROM lineup_players WHERE lineup_id=?", (lineup_id,))
                for entry in record.get("players", []):
                    player_id = players.get(str(entry["player_external_id"]))
                    if not player_id:
                        raise ValueError("Lineup references an unknown player")
                    conn.execute(
                        """INSERT INTO lineup_players(lineup_id, player_id, shirt_number,
                        position_code, starter, field_x, field_y) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            lineup_id,
                            player_id,
                            entry.get("shirt_number"),
                            entry.get("position_code"),
                            int(entry.get("starter", True)),
                            entry.get("field_x"),
                            entry.get("field_y"),
                        ),
                    )
                counts["lineups"] += 1
            for record in payload.get("events", []):
                encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
                external_id = str(
                    record.get("external_id")
                    or sha256(f"{match_id}:{encoded}".encode()).hexdigest()
                )
                conn.execute(
                    """INSERT INTO match_events(match_id, source_provider_id, external_id,
                    event_type, minute, added_minute, team_id, player_id, related_player_id,
                    payload, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_provider_id, external_id) DO UPDATE SET
                    event_type=excluded.event_type, minute=excluded.minute,
                    added_minute=excluded.added_minute, payload=excluded.payload""",
                    (
                        match_id,
                        provider_id,
                        external_id,
                        record["event_type"].upper(),
                        record.get("minute"),
                        record.get("added_minute"),
                        record.get("team_id"),
                        players.get(str(record.get("player_external_id"))),
                        players.get(str(record.get("related_player_external_id"))),
                        json.dumps(record, separators=(",", ":")),
                        record.get("occurred_at"),
                    ),
                )
                counts["events"] += 1
            for record in payload.get("team_statistics", []):
                if record["team_id"] not in match_teams:
                    raise ValueError("Statistics team does not participate in match")
                conn.execute(
                    """INSERT INTO team_match_statistics(match_id, team_id, period, stat_key,
                    stat_value, raw_value, source_provider_id) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, team_id, period, stat_key, source_provider_id)
                    DO UPDATE SET stat_value=excluded.stat_value, raw_value=excluded.raw_value""",
                    (
                        match_id,
                        record["team_id"],
                        record.get("period", "ALL"),
                        record["key"],
                        record.get("value"),
                        record.get("raw"),
                        provider_id,
                    ),
                )
                counts["statistics"] += 1
            for record in payload.get("player_statistics", []):
                player_id = players.get(str(record["player_external_id"]))
                if not player_id:
                    raise ValueError("Statistics reference an unknown player")
                if record["team_id"] not in match_teams:
                    raise ValueError("Player statistics team does not participate in match")
                conn.execute(
                    """INSERT INTO player_match_statistics(
                    match_id, player_id, team_id, stat_key, stat_value, raw_value,
                    source_provider_id) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, player_id, stat_key, source_provider_id)
                    DO UPDATE SET team_id=excluded.team_id, stat_value=excluded.stat_value,
                    raw_value=excluded.raw_value""",
                    (
                        match_id,
                        player_id,
                        record["team_id"],
                        record["key"],
                        record.get("value"),
                        record.get("raw"),
                        provider_id,
                    ),
                )
                counts["player_statistics"] += 1
        return counts
