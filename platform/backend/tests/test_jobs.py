from pathlib import Path

from fais.db import Database
from fais.db.migrate import migrate
from fais.jobs import EventOutbox, JobStore


def test_job_lifecycle_and_durable_outbox(tmp_path: Path) -> None:
    database = Database(tmp_path / "jobs.sqlite3")
    migrate(database)
    jobs = JobStore(database)
    job = jobs.create("PREDICT_MATCH", {"match_id": 7})

    assert job["status"] == "PENDING"
    jobs.running(job["id"])
    jobs.succeeded(job["id"], {"home": 0.5})
    completed = jobs.get(job["id"])
    assert completed is not None
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == {"home": 0.5}

    outbox = EventOutbox(database)
    outbox.add("prediction.completed", job["id"], {"job_id": job["id"]})
    outbox.add("prediction.completed", job["id"], {"ignored": True})
    pending = outbox.pending()
    assert len(pending) == 1
    outbox.published(pending[0]["id"])
    assert outbox.pending() == []
