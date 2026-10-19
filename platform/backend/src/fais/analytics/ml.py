from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fais.db import Database

from .backtest import EvaluatedMatch, classification_metrics
from .features import FeatureBuilder, FeaturePair
from .poisson import RegularizedPoisson, derive_markets, score_matrix

LABELS = ("home", "draw", "away")


def feature_vector(features: FeaturePair) -> list[float]:
    home, away = features.home, features.away
    return [
        float(home.sample_size),
        float(away.sample_size),
        home.goals_for_per_match,
        home.goals_against_per_match,
        home.home_goals_for_per_match,
        home.away_goals_for_per_match,
        away.goals_for_per_match,
        away.goals_against_per_match,
        away.home_goals_for_per_match,
        away.away_goals_for_per_match,
        home.goals_for_per_match - away.goals_against_per_match,
        away.goals_for_per_match - home.goals_against_per_match,
        home.league_goals_per_team_match,
    ]


def promotion_decision(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    minimum_matches: int = 500,
    minimum_relative_log_loss_gain: float = 0.01,
    maximum_ece_regression: float = 0.01,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if candidate["evaluated"] < minimum_matches:
        reasons.append(f"requires at least {minimum_matches} holdout matches")
    maximum_loss = baseline["log_loss"] * (1 - minimum_relative_log_loss_gain)
    if candidate["log_loss"] > maximum_loss:
        reasons.append("log loss did not improve by the required relative margin")
    if candidate["expected_calibration_error"] > (
        baseline["expected_calibration_error"] + maximum_ece_regression
    ):
        reasons.append("calibration regression exceeds the allowed margin")
    return not reasons, reasons


@dataclass(slots=True)
class TrainingResult:
    version: str
    artifact_uri: str
    training_matches: int
    validation_matches: int
    test_matches: int
    baseline: dict[str, Any]
    candidate: dict[str, Any]
    promoted: bool
    promotion_reasons: list[str]


class XGBoostTrainer:
    """CPU-only chronological challenger training with a sealed final holdout."""

    def __init__(self, database: Database, artifact_dir: str | Path):
        self.database = database
        self.artifact_dir = Path(artifact_dir).resolve()

    def run(
        self,
        *,
        min_team_history: int = 3,
        limit: int | None = None,
        promote_if_better: bool = False,
        minimum_matches: int = 500,
    ) -> TrainingResult:
        import numpy as np
        from xgboost import XGBClassifier

        vectors: list[list[float]] = []
        outcomes: list[int] = []
        baselines: list[EvaluatedMatch] = []
        cutoff = ""
        with self.database.connect(readonly=True) as conn:
            sql = """
                SELECT * FROM (
                    SELECT id, home_score, away_score,
                           COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z') AS cutoff
                    FROM matches
                    WHERE status='FINISHED' AND kickoff_date IS NOT NULL
                      AND home_score IS NOT NULL AND away_score IS NOT NULL
                    ORDER BY cutoff DESC, id DESC
            """
            parameters: tuple[int, ...] = ()
            if limit is not None:
                sql += " LIMIT ?"
                parameters = (max(limit, 1),)
            sql += ") ORDER BY cutoff, id"
            targets = conn.execute(sql, parameters).fetchall()
            builder = FeatureBuilder(conn)
            for target in targets:
                features = builder.for_match(target["id"])
                if min(features.home.sample_size, features.away.sample_size) < min_team_history:
                    continue
                outcome = 0 if target["home_score"] > target["away_score"] else 1
                if target["home_score"] < target["away_score"]:
                    outcome = 2
                expected = RegularizedPoisson.predict(features)
                probability = derive_markets(score_matrix(expected))["one_x_two"]
                vectors.append(feature_vector(features))
                outcomes.append(outcome)
                baselines.append(EvaluatedMatch(probability, LABELS[outcome]))
                cutoff = target["cutoff"]
        if len(vectors) < 60 or len(set(outcomes)) != 3:
            raise ValueError("At least 60 eligible matches covering all outcomes are required")
        train_end = int(len(vectors) * 0.70)
        validation_end = int(len(vectors) * 0.85)
        if len(set(outcomes[:train_end])) != 3:
            raise ValueError("Chronological training partition does not cover all outcomes")
        x = np.asarray(vectors, dtype=np.float32)
        y = np.asarray(outcomes, dtype=np.int64)
        model = XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            n_estimators=300,
            max_depth=4,
            learning_rate=0.04,
            min_child_weight=4,
            subsample=0.85,
            colsample_bytree=0.9,
            reg_lambda=2.0,
            eval_metric="mlogloss",
            early_stopping_rounds=25,
            random_state=42,
            n_jobs=2,
            tree_method="hist",
        )
        model.fit(
            x[:train_end],
            y[:train_end],
            eval_set=[(x[train_end:validation_end], y[train_end:validation_end])],
            verbose=False,
        )
        probabilities = model.predict_proba(x[validation_end:])
        evaluated = [
            EvaluatedMatch(dict(zip(LABELS, row, strict=True)), LABELS[int(label)])
            for row, label in zip(probabilities.tolist(), y[validation_end:].tolist(), strict=True)
        ]
        candidate = classification_metrics(evaluated)
        baseline = classification_metrics(baselines[validation_end:])
        promotable, reasons = promotion_decision(
            candidate, baseline, minimum_matches=minimum_matches
        )
        promoted = promote_if_better and promotable
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.artifact_dir / "xgboost-outcome.tmp.json"
        model.save_model(temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        version = f"xgboost-outcome-{digest[:12]}"
        artifact = self.artifact_dir / f"{version}.json"
        temporary.replace(artifact)
        metadata = {
            "candidate": candidate,
            "baseline": baseline,
            "training_matches": train_end,
            "validation_matches": validation_end - train_end,
            "test_matches": len(vectors) - validation_end,
            "random_seed": 42,
            "promotable": promotable,
            "promotion_reasons": reasons,
        }
        with self.database.transaction() as conn:
            if promoted:
                conn.execute("UPDATE model_versions SET active=0 WHERE name='match-outcome'")
            conn.execute(
                """
                INSERT INTO model_versions(
                    name, algorithm, version, artifact_uri, feature_version,
                    training_cutoff_utc, metrics, active
                ) VALUES ('match-outcome', 'xgboost-cpu', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE SET
                    artifact_uri=excluded.artifact_uri, metrics=excluded.metrics,
                    active=excluded.active
                """,
                (
                    version,
                    artifact.as_uri(),
                    FeatureBuilder.version,
                    cutoff,
                    json.dumps(metadata, separators=(",", ":")),
                    int(promoted),
                ),
            )
        return TrainingResult(
            version=version,
            artifact_uri=artifact.as_uri(),
            training_matches=train_end,
            validation_matches=validation_end - train_end,
            test_matches=len(vectors) - validation_end,
            baseline=baseline,
            candidate=candidate,
            promoted=promoted,
            promotion_reasons=reasons,
        )


def load_xgboost_probabilities(artifact_uri: str, features: FeaturePair) -> dict[str, float]:
    import numpy as np
    from xgboost import XGBClassifier

    artifact = Path(artifact_uri.removeprefix("file://"))
    model = XGBClassifier()
    model.load_model(artifact)
    values = model.predict_proba(np.asarray([feature_vector(features)], dtype=np.float32))[0]
    return dict(zip(LABELS, (float(value) for value in values), strict=True))


def torch_outcome_network(input_features: int = 13):
    """Construct the optional PyTorch challenger without importing it in the API runtime."""
    import torch.nn as nn

    return nn.Sequential(
        nn.Linear(input_features, 32),
        nn.ReLU(),
        nn.Dropout(0.1),
        nn.Linear(32, 3),
    )
