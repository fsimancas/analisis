from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from fais.analytics.montecarlo import MonteCarloConfig, MonteCarloSimulator
from fais.api.dependencies import current_analyst, get_repository
from fais.db.repositories import SportsRepository
from fais.jobs import JobStore

router = APIRouter(prefix="/api/v1/analyst", tags=["analyst"])
Analyst = Annotated[dict[str, Any], Depends(current_analyst)]


class SimulationInput(BaseModel):
    iterations: int = Field(default=50_000, ge=1_000, le=100_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class WorkbookInput(BaseModel):
    match_id: int | None = None
    title: str = Field(min_length=2, max_length=160)
    notes: str = Field(default="", max_length=20_000)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/workspace/matches")
def workspace_matches(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    _: Analyst,
    limit: int = 100,
) -> list[dict]:
    return repo.matches(limit=min(max(limit, 1), 500))


@router.post("/workspace/predict/{match_id}", status_code=202)
def predict(match_id: int, request: Request, _: Analyst) -> dict:
    if not request.app.state.repository.match(match_id):
        raise HTTPException(status_code=404, detail="Match not found")
    store = JobStore(request.app.state.database)
    job = store.create("PREDICT_MATCH", {"match_id": match_id})
    celery: Celery = request.app.state.celery
    try:
        celery.send_task("fais.workers.tasks.predict_match", args=[match_id, job["id"]])
    except Exception as error:
        store.failed(job["id"], f"Queue unavailable: {error}")
        raise HTTPException(status_code=503, detail="Prediction queue unavailable") from error
    return store.get(job["id"])  # type: ignore[return-value]


@router.post("/workspace/montecarlo/{match_id}")
def monte_carlo(
    match_id: int,
    body: SimulationInput,
    request: Request,
    user: Analyst,
) -> dict:
    prediction = request.app.state.repository.latest_prediction(match_id)
    if not prediction:
        raise HTTPException(status_code=409, detail="A prediction is required before simulation")
    run_id = str(uuid.uuid4())
    with request.app.state.database.transaction() as conn:
        conn.execute(
            """INSERT INTO analysis_runs(id, user_id, match_id, analysis_type, status,
            parameters, model_version, random_seed)
            VALUES (?, ?, ?, 'MONTE_CARLO', 'RUNNING', ?, ?, ?)""",
            (
                run_id,
                user["id"],
                match_id,
                json.dumps(body.model_dump(), separators=(",", ":")),
                prediction["model_version"],
                body.seed,
            ),
        )
    try:
        result = MonteCarloSimulator.run(
            prediction["home_lambda"],
            prediction["away_lambda"],
            MonteCarloConfig(iterations=body.iterations, seed=body.seed),
        )
    except Exception as error:
        with request.app.state.database.transaction() as conn:
            conn.execute(
                """UPDATE analysis_runs SET status='FAILED', error=?,
                finished_at=CURRENT_TIMESTAMP WHERE id=?""",
                (str(error)[:2000], run_id),
            )
        raise
    with request.app.state.database.transaction() as conn:
        conn.execute(
            """UPDATE analysis_runs SET status='SUCCEEDED', result=?,
            finished_at=CURRENT_TIMESTAMP WHERE id=?""",
            (json.dumps(result, separators=(",", ":")), run_id),
        )
    return {"id": run_id, "match_id": match_id, "result": result}


@router.get("/workspace/runs")
def analysis_runs(request: Request, user: Analyst, match_id: int | None = None) -> list[dict]:
    where = "WHERE user_id=?"
    values: list[int] = [user["id"]]
    if match_id:
        where += " AND match_id=?"
        values.append(match_id)
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            f"SELECT * FROM analysis_runs {where} ORDER BY created_at DESC LIMIT 200", values
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["parameters"] = json.loads(result["parameters"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
    return results


@router.get("/workbooks")
def workbooks(request: Request, user: Analyst) -> list[dict]:
    with request.app.state.database.connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM analyst_workbooks WHERE user_id=? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    results = [dict(row) for row in rows]
    for result in results:
        result["payload"] = json.loads(result["payload"])
    return results


@router.post("/workbooks", status_code=201)
def save_workbook(body: WorkbookInput, request: Request, user: Analyst) -> dict:
    identifier = str(uuid.uuid4())
    with request.app.state.database.transaction() as conn:
        if (
            body.match_id
            and not conn.execute("SELECT 1 FROM matches WHERE id=?", (body.match_id,)).fetchone()
        ):
            raise HTTPException(status_code=404, detail="Match not found")
        row = conn.execute(
            """INSERT INTO analyst_workbooks(id, user_id, match_id, title, notes, payload)
            VALUES (?, ?, ?, ?, ?, ?) RETURNING *""",
            (
                identifier,
                user["id"],
                body.match_id,
                body.title.strip(),
                body.notes,
                json.dumps(body.payload, separators=(",", ":")),
            ),
        ).fetchone()
    result = dict(row)
    result["payload"] = json.loads(result["payload"])
    return result


@router.post("/backtests", status_code=202)
def run_backtest(request: Request, _: Analyst) -> dict:
    store = JobStore(request.app.state.database)
    job = store.create("BACKTEST", {"min_team_history": 3})
    try:
        request.app.state.celery.send_task("fais.workers.tasks.run_backtest", args=[3, job["id"]])
    except Exception as error:
        store.failed(job["id"], f"Queue unavailable: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backtest queue unavailable"
        ) from error
    return store.get(job["id"])  # type: ignore[return-value]


@router.get("/reports/calibration")
def calibration_report(
    repo: Annotated[SportsRepository, Depends(get_repository)], _: Analyst
) -> list[dict]:
    return [
        {
            "id": run["id"],
            "model": run["model"],
            "version": run["version"],
            "evaluated": (run["metrics"] or {}).get("evaluated"),
            "log_loss": (run["metrics"] or {}).get("log_loss"),
            "brier_score": (run["metrics"] or {}).get("brier_score"),
            "expected_calibration_error": (run["metrics"] or {}).get("expected_calibration_error"),
        }
        for run in repo.backtests(limit=100)
    ]
