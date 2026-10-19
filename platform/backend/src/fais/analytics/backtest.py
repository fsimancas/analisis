from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from typing import Any

from fais.db import Database

from .features import FeatureBuilder
from .poisson import RegularizedPoisson, derive_markets, score_matrix


@dataclass(frozen=True, slots=True)
class EvaluatedMatch:
    probability: dict[str, float]
    outcome: str


def classification_metrics(rows: list[EvaluatedMatch]) -> dict[str, Any]:
    if not rows:
        raise ValueError("No matches met the backtest eligibility criteria")
    labels = ("home", "draw", "away")
    log_loss = 0.0
    brier = 0.0
    correct = 0
    calibration: list[list[tuple[float, float]]] = [[] for _ in range(10)]
    outcomes = {label: 0 for label in labels}
    for row in rows:
        outcomes[row.outcome] += 1
        actual_probability = max(row.probability[row.outcome], 1e-15)
        log_loss -= math.log(actual_probability)
        brier += sum(
            (row.probability[label] - float(label == row.outcome)) ** 2 for label in labels
        )
        predicted = max(labels, key=row.probability.__getitem__)
        correct += int(predicted == row.outcome)
        confidence = row.probability[predicted]
        calibration[min(int(confidence * 10), 9)].append(
            (confidence, float(predicted == row.outcome))
        )
    count = len(rows)
    ece = sum(
        (len(bucket) / count)
        * abs(
            sum(confidence for confidence, _ in bucket) / len(bucket)
            - sum(correctness for _, correctness in bucket) / len(bucket)
        )
        for bucket in calibration
        if bucket
    )
    return {
        "evaluated": count,
        "log_loss": round(log_loss / count, 6),
        "brier_score": round(brier / count, 6),
        "accuracy": round(correct / count, 6),
        "expected_calibration_error": round(ece, 6),
        "outcomes": outcomes,
    }


class WalkForwardBacktest:
    """Chronological evaluation; every feature query has a strict target-date cutoff."""

    def __init__(self, database: Database):
        self.database = database

    def run(self, *, min_team_history: int = 3, limit: int | None = None) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self.database.transaction() as conn:
            model = conn.execute(
                """
                SELECT id FROM model_versions
                WHERE version=?
                """,
                (RegularizedPoisson.version,),
            ).fetchone()
            if not model:
                raise ValueError(f"Active model not registered: {RegularizedPoisson.version}")
            bounds = conn.execute(
                """
                SELECT min(kickoff_date), max(kickoff_date) FROM matches
                WHERE status='FINISHED' AND kickoff_date IS NOT NULL
                """
            ).fetchone()
            if not bounds or not bounds[0]:
                raise ValueError("No dated finished matches are available")
            conn.execute(
                """
                INSERT INTO backtest_runs(
                    id, model_version_id, started_at, cutoff_start_utc, cutoff_end_utc, status
                ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, 'RUNNING')
                """,
                (run_id, model[0], bounds[0], bounds[1]),
            )
        skipped = 0
        evaluated: list[EvaluatedMatch] = []
        try:
            with self.database.connect(readonly=True) as conn:
                sql = """
                    SELECT id, home_score, away_score, kickoff_date
                    FROM matches
                    WHERE status='FINISHED' AND kickoff_date IS NOT NULL
                      AND home_score IS NOT NULL AND away_score IS NOT NULL
                    ORDER BY COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z'), id
                """
                parameters: tuple[int, ...] = ()
                if limit is not None:
                    sql += " LIMIT ?"
                    parameters = (max(limit, 1),)
                targets = conn.execute(sql, parameters).fetchall()
                builder = FeatureBuilder(conn)
                for target in targets:
                    features = builder.for_match(target["id"])
                    if min(features.home.sample_size, features.away.sample_size) < min_team_history:
                        skipped += 1
                        continue
                    expected = RegularizedPoisson.predict(features)
                    probabilities = derive_markets(score_matrix(expected))["one_x_two"]
                    outcome = (
                        "home"
                        if target["home_score"] > target["away_score"]
                        else "draw"
                        if target["home_score"] == target["away_score"]
                        else "away"
                    )
                    evaluated.append(EvaluatedMatch(probabilities, outcome))
            metrics = classification_metrics(evaluated)
            metrics.update(
                {
                    "skipped_insufficient_history": skipped,
                    "min_team_history": min_team_history,
                    "model_version": RegularizedPoisson.version,
                    "feature_version": FeatureBuilder.version,
                    "method": "strict-walk-forward",
                }
            )
            with self.database.transaction() as conn:
                conn.execute(
                    """
                    UPDATE backtest_runs SET status='SUCCEEDED', finished_at=CURRENT_TIMESTAMP,
                        metrics=? WHERE id=?
                    """,
                    (json.dumps(metrics, separators=(",", ":")), run_id),
                )
            return {"run_id": run_id, **metrics}
        except Exception as error:
            with self.database.transaction() as conn:
                conn.execute(
                    """
                    UPDATE backtest_runs SET status='FAILED', finished_at=CURRENT_TIMESTAMP,
                        error=? WHERE id=?
                    """,
                    (f"{type(error).__name__}: {error}"[:4000], run_id),
                )
            raise
