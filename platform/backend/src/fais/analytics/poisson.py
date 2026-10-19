from __future__ import annotations

import math
from dataclasses import dataclass

from .features import FeaturePair


@dataclass(frozen=True, slots=True)
class ExpectedGoals:
    home: float
    away: float


class RegularizedPoisson:
    version = "regularized-poisson-v1"

    @staticmethod
    def predict(features: FeaturePair) -> ExpectedGoals:
        prior = max(features.home.league_goals_per_team_match, 0.2)
        home_attack = features.home.home_goals_for_per_match / prior
        away_defense = features.away.goals_against_per_match / prior
        away_attack = features.away.away_goals_for_per_match / prior
        home_defense = features.home.goals_against_per_match / prior
        return ExpectedGoals(
            home=round(max(0.1, min(5.0, prior * 1.08 * home_attack * away_defense)), 6),
            away=round(max(0.1, min(5.0, prior * 0.92 * away_attack * home_defense)), 6),
        )


def poisson_probability(goals: int, expected: float) -> float:
    return math.exp(-expected) * expected**goals / math.factorial(goals)


def score_matrix(expected: ExpectedGoals, max_goals: int = 10) -> list[list[float]]:
    matrix = [
        [
            poisson_probability(home, expected.home) * poisson_probability(away, expected.away)
            for away in range(max_goals + 1)
        ]
        for home in range(max_goals + 1)
    ]
    mass = sum(sum(row) for row in matrix)
    return [[value / mass for value in row] for row in matrix]


def derive_markets(matrix: list[list[float]]) -> dict:
    home = draw = away = btts = over_15 = over_25 = over_35 = 0.0
    scorelines: list[tuple[float, int, int]] = []
    for h, row in enumerate(matrix):
        for a, probability in enumerate(row):
            scorelines.append((probability, h, a))
            if h > a:
                home += probability
            elif h == a:
                draw += probability
            else:
                away += probability
            if h and a:
                btts += probability
            over_15 += probability if h + a > 1.5 else 0.0
            over_25 += probability if h + a > 2.5 else 0.0
            over_35 += probability if h + a > 3.5 else 0.0
    top = sorted(scorelines, reverse=True)[:5]
    return {
        "one_x_two": {"home": home, "draw": draw, "away": away},
        "goals": {
            "over_1_5": over_15,
            "under_1_5": 1 - over_15,
            "over_2_5": over_25,
            "under_2_5": 1 - over_25,
            "over_3_5": over_35,
            "under_3_5": 1 - over_35,
        },
        "btts": {"yes": btts, "no": 1 - btts},
        "top_scorelines": [
            {"home": h, "away": a, "probability": probability} for probability, h, a in top
        ],
    }
