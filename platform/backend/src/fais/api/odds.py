from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from fais.analytics.odds_analysis import analyze_odds
from fais.api.dependencies import competition_scope, get_repository
from fais.db.repositories import SportsRepository

router = APIRouter(prefix="/api/v1/odds", tags=["odds"])
Scope = Annotated[tuple[int, ...] | None, Depends(competition_scope)]


def _rows(request: Request, match_id: int, provider: str | None, latest_only: bool) -> list[dict]:
    clauses = ["o.match_id=?"]
    values: list[Any] = [match_id]
    if provider:
        clauses.append("sp.code=?")
        values.append(provider)
    latest = ""
    if latest_only:
        latest = """AND o.captured_at=(SELECT max(newer.captured_at) FROM odds_snapshots newer
        WHERE newer.match_id=o.match_id AND newer.provider_id=o.provider_id
          AND newer.market_key=o.market_key AND newer.line IS o.line)"""
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            f"""
            SELECT o.*, sp.code AS provider FROM odds_snapshots o
            JOIN source_providers sp ON sp.id=o.provider_id
            WHERE {" AND ".join(clauses)} {latest}
            ORDER BY o.market_key, o.line, o.selection_key, o.captured_at DESC
            """,
            values,
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["raw_payload"] = json.loads(result["raw_payload"]) if result["raw_payload"] else None
    return results


@router.get("/matches/{match_id}")
def match_odds(
    match_id: int,
    request: Request,
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
    provider: str | None = None,
    latest_only: Annotated[bool, Query()] = True,
) -> list[dict]:
    if not repo.match(match_id, scope):
        raise HTTPException(status_code=404, detail="Match not found")
    return _rows(request, match_id, provider, latest_only)


@router.get("/matches/{match_id}/value")
def match_value(
    match_id: int,
    request: Request,
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
    provider: str | None = None,
) -> dict:
    if not repo.match(match_id, scope):
        raise HTTPException(status_code=404, detail="Match not found")
    prediction = repo.latest_prediction(match_id)
    if not prediction:
        raise HTTPException(status_code=409, detail="A prediction is required before odds analysis")
    rows = _rows(request, match_id, provider, True)
    return {
        "match_id": match_id,
        "prediction_id": prediction["id"],
        "model_version": prediction["model_version"],
        "markets": analyze_odds(rows, prediction["payload"]),
    }
