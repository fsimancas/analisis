from __future__ import annotations

from typing import Annotated, Any

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis import Redis

from fais.api.dependencies import (
    competition_scope,
    current_analyst,
    get_database,
    get_repository,
)
from fais.db import Database
from fais.db.repositories import SportsRepository
from fais.jobs import JobStore

router = APIRouter(prefix="/api/v1")
Scope = Annotated[tuple[int, ...] | None, Depends(competition_scope)]
Analyst = Annotated[dict[str, Any], Depends(current_analyst)]


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fais-api"}


@router.get("/readiness", tags=["system"])
def readiness(request: Request) -> dict[str, Any]:
    database: Database = request.app.state.database
    try:
        with database.connect(readonly=True) as conn:
            database_status = conn.execute("PRAGMA quick_check").fetchone()[0]
            pending_outbox = conn.execute(
                "SELECT count(*) FROM event_outbox WHERE published_at IS NULL"
            ).fetchone()[0]
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {error}") from error
    redis_status = "unavailable"
    try:
        client = Redis.from_url(
            request.app.state.settings.redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        redis_status = "ok" if client.ping() else "unavailable"
        client.close()
    except Exception:
        pass
    return {
        "status": "ok" if redis_status == "ok" else "degraded",
        "database": database_status,
        "redis": redis_status,
        "pending_outbox": pending_outbox,
    }


@router.get("/overview", tags=["sports"])
def overview(
    repo: Annotated[SportsRepository, Depends(get_repository)], scope: Scope
) -> dict[str, Any]:
    return repo.overview(scope)


@router.get("/competitions", tags=["sports"])
def competitions(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    return repo.competitions(limit=limit, offset=offset, allowed_competition_ids=scope)


@router.get("/matches", tags=["sports"])
def matches(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
    competition_id: int | None = None,
    team_id: int | None = None,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    return repo.matches(
        competition_id=competition_id,
        team_id=team_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
        allowed_competition_ids=scope,
    )


@router.get("/matches/{match_id}", tags=["sports"])
def match(
    match_id: int, repo: Annotated[SportsRepository, Depends(get_repository)], scope: Scope
) -> dict[str, Any]:
    result = repo.match(match_id, scope)
    if not result:
        raise HTTPException(status_code=404, detail="Match not found")
    return result


@router.get("/matches/{match_id}/prediction", tags=["analytics"])
def latest_prediction(
    match_id: int, repo: Annotated[SportsRepository, Depends(get_repository)], scope: Scope
) -> dict[str, Any]:
    if not repo.match(match_id, scope):
        raise HTTPException(status_code=404, detail="Match not found")
    result = repo.latest_prediction(match_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result


@router.post("/matches/{match_id}/predictions", tags=["analytics"], status_code=202)
def enqueue_prediction(
    match_id: int,
    request: Request,
    database: Annotated[Database, Depends(get_database)],
    _: Analyst,
) -> dict[str, Any]:
    repo: SportsRepository = request.app.state.repository
    if not repo.match(match_id):
        raise HTTPException(status_code=404, detail="Match not found")
    store = JobStore(database)
    job = store.create("PREDICT_MATCH", {"match_id": match_id})
    celery: Celery = request.app.state.celery
    try:
        celery.send_task("fais.workers.tasks.predict_match", args=[match_id, job["id"]])
    except Exception as error:
        store.failed(job["id"], f"Queue unavailable: {error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction queue unavailable",
        ) from error
    return store.get(job["id"])  # type: ignore[return-value]


@router.get("/jobs/{job_id}", tags=["system"])
def job(
    job_id: str,
    database: Annotated[Database, Depends(get_database)],
    _: Analyst,
) -> dict[str, Any]:
    result = JobStore(database).get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.get("/quality/issues", tags=["quality"])
def quality_issues(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    _: Analyst,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    return repo.quality_issues(limit=limit, offset=offset)


@router.get("/models", tags=["analytics"])
def models(
    repo: Annotated[SportsRepository, Depends(get_repository)], _: Analyst
) -> list[dict[str, Any]]:
    return repo.models()


@router.get("/teams", tags=["sports"])
def teams(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    scope: Scope,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    return repo.teams(search=search, limit=limit, offset=offset, allowed_competition_ids=scope)


@router.get("/teams/{team_id}", tags=["sports"])
def team(
    team_id: int, repo: Annotated[SportsRepository, Depends(get_repository)], scope: Scope
) -> dict[str, Any]:
    result = repo.team(team_id, scope)
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    return result


@router.get("/backtests", tags=["analytics"])
def backtests(
    repo: Annotated[SportsRepository, Depends(get_repository)],
    _: Analyst,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    return repo.backtests(limit=limit)
