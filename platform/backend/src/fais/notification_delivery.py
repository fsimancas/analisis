from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen

from fais.db import Database


@dataclass(slots=True)
class DeliverySummary:
    delivered: int = 0
    failed: int = 0


class WebhookNotifier:
    def __init__(self, url: str, token: str | None = None, timeout: float = 5.0):
        self.url = url
        self.token = token
        self.timeout = timeout

    def send(self, payload: dict) -> None:
        headers = {"Content-Type": "application/json", "User-Agent": "FAIS/0.1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            self.url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Webhook returned HTTP {response.status}")


def dispatch_webhook_notifications(
    database: Database,
    notifier: WebhookNotifier,
    *,
    limit: int = 100,
) -> DeliverySummary:
    with database.connect(readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT n.id, n.event_key, n.title, n.payload, n.created_at,
                   u.email, COALESCE(d.attempts, 0) AS attempts
            FROM notifications n
            JOIN users u ON u.id=n.user_id
            LEFT JOIN notification_deliveries d
              ON d.notification_id=n.id AND d.channel='WEBHOOK'
            WHERE d.id IS NULL OR (
                d.status='FAILED' AND d.attempts < 8
                AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= CURRENT_TIMESTAMP)
            )
            ORDER BY n.id LIMIT ?
            """,
            (min(max(limit, 1), 1000),),
        ).fetchall()
    summary = DeliverySummary()
    for row in rows:
        payload = {
            "notification_id": row["id"],
            "event_key": row["event_key"],
            "title": row["title"],
            "recipient": row["email"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
        }
        attempts = row["attempts"] + 1
        try:
            notifier.send(payload)
        except Exception as error:
            delay = min(60 * (2 ** min(attempts - 1, 6)), 3600)
            with database.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO notification_deliveries(
                        notification_id, channel, status, attempts, error, next_attempt_at
                    ) VALUES (?, 'WEBHOOK', 'FAILED', ?, ?, datetime('now', ?))
                    ON CONFLICT(notification_id, channel) DO UPDATE SET
                        status='FAILED', attempts=excluded.attempts, error=excluded.error,
                        next_attempt_at=excluded.next_attempt_at, updated_at=CURRENT_TIMESTAMP
                    """,
                    (row["id"], attempts, str(error)[:1000], f"+{delay} seconds"),
                )
            summary.failed += 1
            continue
        with database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO notification_deliveries(
                    notification_id, channel, status, attempts, delivered_at
                ) VALUES (?, 'WEBHOOK', 'DELIVERED', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(notification_id, channel) DO UPDATE SET
                    status='DELIVERED', attempts=excluded.attempts, error=NULL,
                    next_attempt_at=NULL, delivered_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (row["id"], attempts),
            )
        summary.delivered += 1
    return summary
