from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonteCarloConfig:
    iterations: int = 50_000
    seed: int = 42

    def __post_init__(self) -> None:
        if not 1_000 <= self.iterations <= 100_000:
            raise ValueError("iterations must be between 1000 and 100000")


def _poisson(rng: random.Random, expected: float) -> int:
    threshold = math.exp(-expected)
    product = 1.0
    value = -1
    while product > threshold:
        value += 1
        product *= rng.random()
    return value


class MonteCarloSimulator:
    version = "monte-carlo-poisson-v1"

    @staticmethod
    def run(home_lambda: float, away_lambda: float, config: MonteCarloConfig) -> dict:
        if home_lambda <= 0 or away_lambda <= 0:
            raise ValueError("Expected goals must be positive")
        rng = random.Random(config.seed)
        outcomes = Counter[str]()
        totals = Counter[str]()
        scorelines = Counter[tuple[int, int]]()
        home_goals = away_goals = 0
        for _ in range(config.iterations):
            home = _poisson(rng, home_lambda)
            away = _poisson(rng, away_lambda)
            home_goals += home
            away_goals += away
            scorelines[(home, away)] += 1
            outcomes["home" if home > away else "draw" if home == away else "away"] += 1
            totals["over_1_5"] += int(home + away > 1.5)
            totals["over_2_5"] += int(home + away > 2.5)
            totals["over_3_5"] += int(home + away > 3.5)
            totals["btts_yes"] += int(home > 0 and away > 0)
        denominator = float(config.iterations)
        top = scorelines.most_common(10)
        return {
            "version": MonteCarloSimulator.version,
            "iterations": config.iterations,
            "seed": config.seed,
            "expected_goals": {
                "home": home_goals / denominator,
                "away": away_goals / denominator,
            },
            "one_x_two": {key: outcomes[key] / denominator for key in ("home", "draw", "away")},
            "markets": {
                **{key: totals[key] / denominator for key in ("over_1_5", "over_2_5", "over_3_5")},
                "under_1_5": 1 - totals["over_1_5"] / denominator,
                "under_2_5": 1 - totals["over_2_5"] / denominator,
                "under_3_5": 1 - totals["over_3_5"] / denominator,
                "btts_yes": totals["btts_yes"] / denominator,
                "btts_no": 1 - totals["btts_yes"] / denominator,
            },
            "top_scorelines": [
                {"home": score[0], "away": score[1], "probability": count / denominator}
                for score, count in top
            ],
        }
