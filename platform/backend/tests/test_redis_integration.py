from __future__ import annotations

import os
from pathlib import Path
from threading import Thread
from time import sleep

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from fais.api.app import create_app
from fais.config import Settings
from fais.events import EventPublisher

REDIS_URL = os.getenv("FAIS_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="FAIS_TEST_REDIS_URL is not configured")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "redis-integration.sqlite3",
        redis_url=REDIS_URL or "redis://127.0.0.1:6379/14",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
    )


def test_event_publisher_writes_topic_and_platform_streams() -> None:
    assert REDIS_URL is not None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    redis.flushdb()

    event_id = EventPublisher(REDIS_URL).publish("scores", {"match_id": 42, "home": 2})

    topic = redis.xrange("fais:scores")
    platform = redis.xrange("fais:platform")
    assert topic[0][0] == event_id
    assert '"match_id":42' in topic[0][1]["payload"]
    assert platform[0][1]["topic"] == "scores"


def test_websocket_bridges_a_live_redis_stream(tmp_path: Path) -> None:
    assert REDIS_URL is not None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    redis.flushdb()

    def publish() -> None:
        sleep(0.1)
        EventPublisher(REDIS_URL).publish("live", {"score": "1-0"})

    with (
        TestClient(create_app(_settings(tmp_path))) as client,
        client.websocket_connect("/ws/live") as websocket,
    ):
        publisher = Thread(target=publish, daemon=True)
        publisher.start()
        message = websocket.receive_json()
        publisher.join(timeout=2)

    assert message["topic"] == "live"
    assert message["payload"] == {"score": "1-0"}
