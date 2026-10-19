from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from fais.db import Database


@dataclass(slots=True)
class JobStore:
    database: Database

    def create(self, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO jobs(id, job_type, status, payload) VALUES (?, ?, 'PENDING', ?)",
                (job_id, job_type, json.dumps(payload, separators=(",", ":"))),
            )
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.database.connect(readonly=True) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def running(self, job_id: str) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status='RUNNING', started_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )

    def succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE jobs SET status='SUCCEEDED', result=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (json.dumps(result, separators=(",", ":")), job_id),
            )

    def failed(self, job_id: str, error: str) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE jobs SET status='FAILED', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?
                """,
                (error[:4000], job_id),
            )


@dataclass(slots=True)
class EventOutbox:
    database: Database

    def add(self, topic: str, event_key: str, payload: dict[str, Any]) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO event_outbox(topic, event_key, payload) VALUES (?, ?, ?)
                ON CONFLICT(topic, event_key) DO NOTHING
                """,
                (topic, event_key, json.dumps(payload, separators=(",", ":"))),
            )

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, topic, event_key, payload FROM event_outbox
                WHERE published_at IS NULL ORDER BY id LIMIT ?
                """,
                (min(max(limit, 1), 1000),),
            ).fetchall()
        return [dict(row) for row in rows]

    def published(self, event_id: int) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE event_outbox SET published_at=CURRENT_TIMESTAMP WHERE id=?",
                (event_id,),
            )
