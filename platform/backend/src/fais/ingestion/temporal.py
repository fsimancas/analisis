from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

_ISO_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S")
_FULL_DATE = re.compile(
    r"^(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})"
    r"(?:\s+(?P<hour>\d{2}):(?P<minute>\d{2}))?"
)
_PARTIAL_DATETIME = re.compile(
    r"^(?P<day>\d{2})\.(?P<month>\d{2})\.\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})"
)
_PARTIAL_DATE = re.compile(r"^(?P<day>\d{2})\.(?P<month>\d{2})\.")


@dataclass(frozen=True, slots=True)
class ParsedKickoff:
    utc: str | None
    local_date: str | None
    timezone: str | None
    precision: str
    year_inferred: bool = False
    suffix: str | None = None


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _localized(
    *, year: int, month: int, day: int, hour: int, minute: int, timezone: str
) -> ParsedKickoff:
    local = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone))
    return ParsedKickoff(
        utc=local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        local_date=local.date().isoformat(),
        timezone=timezone,
        precision="MINUTE",
    )


def parse_kickoff(
    value: str | None,
    *,
    reference_date: date | None = None,
    source_timezone: str = "America/Bogota",
) -> ParsedKickoff:
    """Normalize legacy timestamps while preserving their actual precision."""
    if not value or not value.strip():
        return ParsedKickoff(None, None, None, "UNKNOWN")
    raw = value.strip()
    iso = raw.replace("Z", "+0000")
    for fmt in _ISO_FORMATS:
        try:
            parsed = datetime.strptime(iso, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
        return ParsedKickoff(
            parsed.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            parsed.date().isoformat(),
            source_timezone if parsed.utcoffset() != UTC.utcoffset(parsed) else "UTC",
            "MINUTE",
        )
    try:
        parsed_date = date.fromisoformat(raw)
    except ValueError:
        pass
    else:
        return ParsedKickoff(None, parsed_date.isoformat(), None, "DATE")

    match = _FULL_DATE.match(raw)
    inferred = False
    if not match:
        match = _PARTIAL_DATETIME.match(raw)
        inferred = bool(match)
    if match:
        values = match.groupdict()
        explicit_year = values.get("year")
        year = (
            int(explicit_year) if explicit_year else reference_date.year if reference_date else None
        )
        if year is None:
            return ParsedKickoff(None, None, None, "UNKNOWN")
        valid_date = _date(year, int(values["month"]), int(values["day"]))
        if not valid_date:
            return ParsedKickoff(None, None, None, "UNKNOWN")
        suffix = raw[match.end() :].strip() or None
        if values.get("hour") is None:
            return ParsedKickoff(None, valid_date.isoformat(), None, "DATE", inferred, suffix)
        parsed = _localized(
            year=year,
            month=valid_date.month,
            day=valid_date.day,
            hour=int(values["hour"]),
            minute=int(values["minute"]),
            timezone=source_timezone,
        )
        return ParsedKickoff(
            parsed.utc,
            parsed.local_date,
            parsed.timezone,
            parsed.precision,
            inferred,
            suffix,
        )

    match = _PARTIAL_DATE.match(raw)
    if match and reference_date:
        valid_date = _date(reference_date.year, int(match["month"]), int(match["day"]))
        if valid_date:
            return ParsedKickoff(
                None,
                valid_date.isoformat(),
                None,
                "DATE",
                True,
                raw[match.end() :].strip() or None,
            )
    return ParsedKickoff(None, None, None, "UNKNOWN")
