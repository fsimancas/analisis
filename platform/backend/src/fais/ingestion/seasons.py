from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SeasonRange:
    name: str
    starts_at: str
    ends_at: str
    confidence: float


def season_from_range(first: str, last: str) -> SeasonRange:
    start = date.fromisoformat(first)
    end = date.fromisoformat(last)
    if start.year == end.year:
        return SeasonRange(str(start.year), first, last, 0.95)
    if end.year == start.year + 1 and start.month >= 6 and end.month <= 7:
        return SeasonRange(f"{start.year}/{str(end.year)[2:]}", first, last, 0.95)
    return SeasonRange(f"{start.year}-{end.year}", first, last, 0.85)


def assign_dataset_seasons(conn: sqlite3.Connection) -> int:
    """Assign the snapshot's observed competition cycle without claiming an external season ID."""
    assigned = 0
    ranges = conn.execute(
        """
        SELECT competition_id, min(kickoff_date), max(kickoff_date)
        FROM matches WHERE kickoff_date IS NOT NULL GROUP BY competition_id
        """
    ).fetchall()
    for competition_id, first, last in ranges:
        season = season_from_range(first, last)
        existing = conn.execute(
            """
            SELECT id FROM seasons
            WHERE competition_id=? AND assignment_method='dataset-range-v1'
            """,
            (competition_id,),
        ).fetchone()
        if existing:
            season_id = existing[0]
            conn.execute(
                """
                UPDATE seasons SET name=?, starts_at=?, ends_at=?, confidence=? WHERE id=?
                """,
                (season.name, season.starts_at, season.ends_at, season.confidence, season_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO seasons(
                    competition_id, name, starts_at, ends_at, assignment_method, confidence
                ) VALUES (?, ?, ?, ?, 'dataset-range-v1', ?)
                """,
                (
                    competition_id,
                    season.name,
                    season.starts_at,
                    season.ends_at,
                    season.confidence,
                ),
            )
            season_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "UPDATE matches SET season_id=? WHERE competition_id=?",
            (season_id, competition_id),
        )
        assigned += 1
    return assigned
