from __future__ import annotations

import json
from typing import Any

from fais.db import Database

_EVENT_ALERTS = {
    "prediction.completed": ("PREDICTION_READY", "Predicción disponible"),
    "match.kickoff": ("KICKOFF", "El partido ha comenzado"),
    "match.goal": ("GOAL", "Gol en el partido"),
    "match.full_time": ("FULL_TIME", "Partido finalizado"),
    "odds.movement": ("ODDS_MOVEMENT", "Movimiento de cuota"),
}


def create_notifications(
    database: Database, topic: str, event_key: str, payload: dict[str, Any]
) -> int:
    mapped = _EVENT_ALERTS.get(topic)
    match_id = payload.get("match_id")
    if not mapped or match_id is None:
        return 0
    event_type, title = mapped
    encoded = json.dumps(payload, separators=(",", ":"))
    created = 0
    with database.transaction() as conn:
        alerts = conn.execute(
            """
            SELECT id, user_id FROM alerts
            WHERE match_id=? AND event_type=? AND active=1
            """,
            (match_id, event_type),
        ).fetchall()
        for alert in alerts:
            created += conn.execute(
                """
                INSERT INTO notifications(user_id, alert_id, event_key, title, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(alert_id, event_key) DO NOTHING
                """,
                (alert["user_id"], alert["id"], event_key, title, encoded),
            ).rowcount
    return created
