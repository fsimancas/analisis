from __future__ import annotations

import json
from dataclasses import asdict

from fais.db.connection import Database

from .features import FeatureBuilder
from .ml import load_xgboost_probabilities
from .poisson import RegularizedPoisson, derive_markets, score_matrix


class PredictionEngine:
    def __init__(self, database: Database):
        self.database = database

    def predict(self, match_id: int) -> dict:
        with self.database.transaction() as conn:
            features = FeatureBuilder(conn).for_match(match_id)
            active_model = conn.execute(
                """
                SELECT algorithm, version, artifact_uri FROM model_versions
                WHERE name='match-outcome' AND active=1
                """
            ).fetchone()
            if not active_model:
                raise ValueError("No active match-outcome model is registered")
            expected = RegularizedPoisson.predict(features)
            matrix = score_matrix(expected)
            markets = derive_markets(matrix)
            if active_model["algorithm"] == "xgboost-cpu":
                markets["one_x_two"] = load_xgboost_probabilities(
                    active_model["artifact_uri"], features
                )
            payload = {
                "expected_goals": asdict(expected),
                "markets": markets,
                "score_matrix": matrix,
                "samples": {
                    "home": features.home.sample_size,
                    "away": features.away.sample_size,
                },
            }
            cutoff = features.home.cutoff_utc
            for team in (features.home, features.away):
                conn.execute(
                    """
                    INSERT INTO feature_snapshots(
                        match_id, team_id, cutoff_utc, feature_version, payload, input_hash
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, team_id, cutoff_utc, feature_version)
                    DO UPDATE SET payload=excluded.payload, input_hash=excluded.input_hash
                    """,
                    (
                        match_id,
                        team.team_id,
                        cutoff,
                        FeatureBuilder.version,
                        json.dumps(team.payload(), sort_keys=True),
                        features.input_hash,
                    ),
                )
            conn.execute(
                """
                INSERT INTO predictions(
                    match_id, cutoff_utc, model_version, feature_version, status,
                    home_lambda, away_lambda, payload, input_hash
                ) VALUES (?, ?, ?, ?, 'READY', ?, ?, ?, ?)
                ON CONFLICT(match_id, cutoff_utc, model_version, feature_version, input_hash)
                DO UPDATE SET payload=excluded.payload, status='READY'
                """,
                (
                    match_id,
                    cutoff,
                    active_model["version"],
                    FeatureBuilder.version,
                    expected.home,
                    expected.away,
                    json.dumps(payload, sort_keys=True),
                    features.input_hash,
                ),
            )
        return payload
