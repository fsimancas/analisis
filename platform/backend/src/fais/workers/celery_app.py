from celery import Celery

from fais.config import Settings

settings = Settings.from_env()
celery_app = Celery("fais", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "fais.workers.tasks.import_legacy": {"queue": "writer"},
        "fais.workers.tasks.predict_match": {"queue": "writer"},
        "fais.workers.tasks.ingest_json": {"queue": "writer"},
        "fais.workers.tasks.ingest_provider_file": {"queue": "writer"},
        "fais.workers.tasks.dispatch_outbox": {"queue": "writer"},
        "fais.workers.tasks.scan_inbox": {"queue": "writer"},
        "fais.workers.tasks.dispatch_notifications": {"queue": "writer"},
        "fais.workers.tasks.run_backtest": {"queue": "writer"},
        "fais.workers.tasks.train_xgboost": {"queue": "writer"},
    },
    beat_schedule={
        "dispatch-durable-outbox": {
            "task": "fais.workers.tasks.dispatch_outbox",
            "schedule": 10.0,
        },
        "scan-json-inbox": {
            "task": "fais.workers.tasks.scan_inbox",
            "schedule": 60.0,
        },
        "dispatch-user-notifications": {
            "task": "fais.workers.tasks.dispatch_notifications",
            "schedule": 15.0,
        },
    },
)
celery_app.autodiscover_tasks(["fais.workers"])
