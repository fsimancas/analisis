from __future__ import annotations

from dataclasses import asdict

from fais.analytics import PredictionEngine, WalkForwardBacktest
from fais.analytics.ml import XGBoostTrainer
from fais.config import Settings
from fais.db import Database
from fais.db.migrate import migrate
from fais.events import EventPublisher, dispatch_pending
from fais.ingestion import LegacyImporter
from fais.ingestion.inbox import InboxScanner
from fais.ingestion.json_feed import JsonMatchFeed
from fais.jobs import EventOutbox, JobStore
from fais.notification_delivery import WebhookNotifier, dispatch_webhook_notifications
from fais.notifications import create_notifications

from .celery_app import celery_app


def _runtime():
    settings = Settings.from_env()
    database = Database(settings.database_path)
    migrate(database)
    return settings, database


def _complete_job(database: Database, job_id: str | None, result: dict) -> None:
    if job_id:
        JobStore(database).succeeded(job_id, result)
        with database.transaction() as conn:
            conn.execute(
                "UPDATE admin_uploads SET status='SUCCEEDED', error=NULL WHERE job_id=?",
                (job_id,),
            )


def _fail_job(database: Database, job_id: str | None, error: Exception) -> None:
    if job_id:
        JobStore(database).failed(job_id, f"{type(error).__name__}: {error}")
        with database.transaction() as conn:
            conn.execute(
                "UPDATE admin_uploads SET status='FAILED', error=? WHERE job_id=?",
                (str(error)[:1000], job_id),
            )


def _emit(database: Database, settings: Settings, topic: str, key: str, payload: dict) -> None:
    create_notifications(database, topic, key, payload)
    outbox = EventOutbox(database)
    outbox.add(topic, key, payload)
    try:
        dispatch_pending(outbox, EventPublisher(settings.redis_url))
    except Exception:
        # The durable outbox is retried independently when Redis recovers.
        return


@celery_app.task(name="fais.workers.tasks.import_legacy")
def import_legacy(source_path: str, job_id: str | None = None) -> dict:
    settings, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = asdict(LegacyImporter(database).run(source_path))
        _complete_job(database, job_id, result)
        _emit(database, settings, "ingestion.completed", job_id or source_path, result)
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise


@celery_app.task(name="fais.workers.tasks.predict_match")
def predict_match(match_id: int, job_id: str | None = None) -> dict:
    settings, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = PredictionEngine(database).predict(match_id)
        _complete_job(database, job_id, result)
        _emit(
            database,
            settings,
            "prediction.completed",
            job_id or str(match_id),
            {"match_id": match_id, "result": result},
        )
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise


@celery_app.task(name="fais.workers.tasks.dispatch_outbox")
def dispatch_outbox(limit: int = 100) -> dict[str, int]:
    settings, database = _runtime()
    count = dispatch_pending(EventOutbox(database), EventPublisher(settings.redis_url), limit)
    return {"published": count}


@celery_app.task(name="fais.workers.tasks.scan_inbox")
def scan_inbox(job_id: str | None = None) -> dict:
    settings, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = asdict(InboxScanner(database, settings.inbox_path).scan())
        _complete_job(database, job_id, result)
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise


@celery_app.task(name="fais.workers.tasks.dispatch_notifications")
def dispatch_notifications(limit: int = 100) -> dict:
    settings, database = _runtime()
    with database.connect(readonly=True) as conn:
        channel = conn.execute(
            "SELECT webhook_url FROM alert_channels WHERE enabled=1 ORDER BY id LIMIT 1"
        ).fetchone()
    webhook_url = channel["webhook_url"] if channel else settings.alert_webhook_url
    if not webhook_url:
        return {"configured": False, "delivered": 0, "failed": 0}
    result = dispatch_webhook_notifications(
        database,
        WebhookNotifier(webhook_url, settings.alert_webhook_token),
        limit=limit,
    )
    return {"configured": True, **asdict(result)}


@celery_app.task(name="fais.workers.tasks.run_backtest")
def run_backtest(min_team_history: int = 3, job_id: str | None = None) -> dict:
    _, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = WalkForwardBacktest(database).run(min_team_history=min_team_history)
        _complete_job(database, job_id, result)
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise


@celery_app.task(name="fais.workers.tasks.train_xgboost")
def train_xgboost(promote: bool = False, job_id: str | None = None) -> dict:
    _, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = asdict(
            XGBoostTrainer(database, database.path.parent / "models").run(
                promote_if_better=promote
            )
        )
        _complete_job(database, job_id, result)
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise


@celery_app.task(name="fais.workers.tasks.ingest_json")
def ingest_json(
    source_path: str,
    country_slug: str,
    competition_slug: str,
    captured_on: str,
    job_id: str | None = None,
) -> dict:
    from datetime import date

    settings, database = _runtime()
    store = JobStore(database)
    if job_id:
        store.running(job_id)
    try:
        result = asdict(
            JsonMatchFeed(database).run(
                source_path,
                country_slug=country_slug,
                competition_slug=competition_slug,
                captured_on=date.fromisoformat(captured_on),
            )
        )
        _complete_job(database, job_id, result)
        _emit(database, settings, "ingestion.completed", job_id or source_path, result)
        return result
    except Exception as error:
        _fail_job(database, job_id, error)
        raise
