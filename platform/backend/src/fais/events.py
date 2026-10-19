from __future__ import annotations

import json

from redis import Redis

from fais.jobs import EventOutbox


class EventPublisher:
    def __init__(self, redis_url: str):
        self.client = Redis.from_url(redis_url, decode_responses=True)

    def publish(self, topic: str, payload: dict) -> str:
        encoded = json.dumps(payload, separators=(",", ":"))
        event_id = self.client.xadd(
            f"fais:{topic}",
            {"payload": encoded},
            maxlen=10_000,
            approximate=True,
        )
        if topic != "platform":
            self.client.xadd(
                "fais:platform",
                {"topic": topic, "payload": encoded},
                maxlen=10_000,
                approximate=True,
            )
        return event_id


def dispatch_pending(outbox: EventOutbox, publisher: EventPublisher, limit: int = 100) -> int:
    """Publish durable events in order; leave the first failed event for a retry."""
    sent = 0
    for event in outbox.pending(limit):
        publisher.publish(event["topic"], json.loads(event["payload"]))
        outbox.published(event["id"])
        sent += 1
    return sent
