from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MatchStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class MatchType(StrEnum):
    RESULT = "RESULT"
    UPCOMING = "UPCOMING"


class QualitySeverity(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class Score:
    home: int
    away: int

    def __post_init__(self) -> None:
        if self.home < 0 or self.away < 0:
            raise ValueError("A score cannot contain negative goals")
