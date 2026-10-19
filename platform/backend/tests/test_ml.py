from __future__ import annotations

from fais.analytics.features import FeaturePair, TeamFeatures
from fais.analytics.ml import feature_vector, promotion_decision


def test_feature_vector_is_stable_and_contains_no_target_result() -> None:
    common = {
        "cutoff_utc": "2026-01-01T00:00:00Z",
        "sample_size": 10,
        "goals_for_per_match": 1.5,
        "goals_against_per_match": 1.1,
        "home_goals_for_per_match": 1.7,
        "away_goals_for_per_match": 1.2,
        "league_goals_per_team_match": 1.3,
    }
    pair = FeaturePair(
        TeamFeatures(team_id=1, **common),
        TeamFeatures(team_id=2, **common),
        "hash",
    )
    vector = feature_vector(pair)
    assert len(vector) == 13
    assert vector[:2] == [10.0, 10.0]
    assert vector[-1] == 1.3


def test_promotion_requires_sample_gain_and_calibration() -> None:
    baseline = {
        "evaluated": 1000,
        "log_loss": 1.0,
        "expected_calibration_error": 0.03,
    }
    good = {
        "evaluated": 1000,
        "log_loss": 0.98,
        "expected_calibration_error": 0.035,
    }
    weak = {
        "evaluated": 100,
        "log_loss": 0.999,
        "expected_calibration_error": 0.08,
    }
    assert promotion_decision(good, baseline)[0] is True
    promoted, reasons = promotion_decision(weak, baseline)
    assert promoted is False
    assert len(reasons) == 3
