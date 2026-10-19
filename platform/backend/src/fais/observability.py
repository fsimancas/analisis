from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from redis import Redis

from fais.db import Database


@dataclass(slots=True)
class RequestMetrics:
    started_at: float = field(default_factory=time.monotonic)
    requests: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, status_code: int, duration: float) -> None:
        with self._lock:
            self.requests += 1
            self.errors += int(status_code >= 500)
            self.duration_seconds += duration

    def prometheus(self) -> str:
        with self._lock:
            uptime = time.monotonic() - self.started_at
            values = (
                "# HELP fais_uptime_seconds Process uptime.\n"
                "# TYPE fais_uptime_seconds gauge\n"
                f"fais_uptime_seconds {uptime:.3f}\n"
                "# HELP fais_http_requests_total HTTP requests handled.\n"
                "# TYPE fais_http_requests_total counter\n"
                f"fais_http_requests_total {self.requests}\n"
                "# HELP fais_http_errors_total HTTP 5xx responses.\n"
                "# TYPE fais_http_errors_total counter\n"
                f"fais_http_errors_total {self.errors}\n"
                "# HELP fais_http_duration_seconds_total Accumulated request duration.\n"
                "# TYPE fais_http_duration_seconds_total counter\n"
                f"fais_http_duration_seconds_total {self.duration_seconds:.6f}\n"
            )
        return values


def system_metrics(database: Database, redis_url: str) -> str:
    gauges = {
        "fais_database_up": 0,
        "fais_redis_up": 0,
        "fais_outbox_pending": 0,
        "fais_jobs_pending": 0,
        "fais_feed_files_failed": 0,
        "fais_notification_deliveries_failed": 0,
    }
    try:
        with database.connect(readonly=True) as conn:
            database_status = conn.execute("PRAGMA quick_check").fetchone()[0]
            gauges["fais_database_up"] = int(database_status == "ok")
            gauges["fais_outbox_pending"] = conn.execute(
                "SELECT count(*) FROM event_outbox WHERE published_at IS NULL"
            ).fetchone()[0]
            gauges["fais_jobs_pending"] = conn.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('PENDING', 'RUNNING')"
            ).fetchone()[0]
            gauges["fais_feed_files_failed"] = conn.execute(
                "SELECT count(*) FROM feed_files WHERE status='FAILED'"
            ).fetchone()[0]
            gauges["fais_notification_deliveries_failed"] = conn.execute(
                "SELECT count(*) FROM notification_deliveries WHERE status='FAILED'"
            ).fetchone()[0]
    except Exception:
        pass
    try:
        client = Redis.from_url(redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
        gauges["fais_redis_up"] = int(bool(client.ping()))
        client.close()
    except Exception:
        pass
    lines: list[str] = []
    for name, value in gauges.items():
        lines.extend((f"# TYPE {name} gauge", f"{name} {value}"))
    return "\n".join(lines) + "\n"
