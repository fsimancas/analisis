from __future__ import annotations

from collections import defaultdict
from typing import Any


def _model_probability(payload: dict[str, Any], market: str, selection: str) -> float | None:
    markets = payload.get("markets", {})
    market_key = market.upper()
    selection_key = selection.upper()
    if market_key in {"1X2", "MATCH_RESULT"}:
        key = {
            "HOME": "home",
            "1": "home",
            "DRAW": "draw",
            "X": "draw",
            "AWAY": "away",
            "2": "away",
        }.get(selection_key)
        return markets.get("one_x_two", {}).get(key) if key else None
    if market_key in {"TOTAL_1_5", "TOTAL_2_5", "TOTAL_3_5"}:
        line = market_key.removeprefix("TOTAL_").lower()
        key = f"{selection_key.lower()}_{line}"
        return markets.get("goals", {}).get(key)
    if market_key in {"BTTS", "BOTH_TEAMS_TO_SCORE"}:
        key = "yes" if selection_key in {"YES", "SI", "SÍ"} else "no"
        return markets.get("btts", {}).get(key)
    return None


def analyze_odds(
    rows: list[dict[str, Any]], prediction_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Calculate overround, fair implied probability and model expected value."""
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["provider_id"], row["market_key"], row.get("line"), row["captured_at"])].append(
            row
        )
    results: list[dict[str, Any]] = []
    for group in groups.values():
        overround = sum(1 / float(row["decimal_odd"]) for row in group)
        for row in group:
            odd = float(row["decimal_odd"])
            implied = 1 / odd
            model = _model_probability(prediction_payload, row["market_key"], row["selection_key"])
            enriched = dict(row)
            enriched.update(
                {
                    "implied_probability": implied,
                    "fair_implied_probability": implied / overround if overround else implied,
                    "overround": overround,
                    "model_probability": model,
                    "expected_value": model * odd - 1 if model is not None else None,
                    "edge": model - implied / overround
                    if model is not None and overround
                    else None,
                }
            )
            results.append(enriched)
    return sorted(
        results,
        key=lambda row: row["expected_value"] if row["expected_value"] is not None else -999,
        reverse=True,
    )
