from datetime import date

from fais.ingestion.temporal import parse_kickoff


def test_partial_flashscore_time_uses_capture_year_and_source_timezone() -> None:
    parsed = parse_kickoff(
        "18.10. 14:30Tras pen.",
        reference_date=date(2026, 10, 18),
        source_timezone="America/Bogota",
    )
    assert parsed.utc == "2026-10-18T19:30:00Z"
    assert parsed.local_date == "2026-10-18"
    assert parsed.precision == "MINUTE"
    assert parsed.year_inferred is True
    assert parsed.suffix == "Tras pen."


def test_explicit_date_does_not_invent_a_time() -> None:
    parsed = parse_kickoff("13.03.2027")
    assert parsed.utc is None
    assert parsed.local_date == "2027-03-13"
    assert parsed.precision == "DATE"
    assert parsed.year_inferred is False


def test_partial_date_without_reference_remains_unknown() -> None:
    parsed = parse_kickoff("18.10. 14:30")
    assert parsed.precision == "UNKNOWN"
