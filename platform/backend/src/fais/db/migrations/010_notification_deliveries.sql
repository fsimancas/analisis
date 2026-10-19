CREATE TABLE notification_deliveries (
    id INTEGER PRIMARY KEY,
    notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK(channel IN ('WEBHOOK')),
    status TEXT NOT NULL CHECK(status IN ('DELIVERED', 'FAILED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    next_attempt_at TEXT,
    delivered_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(notification_id, channel)
) STRICT;

CREATE INDEX idx_notification_deliveries_retry
ON notification_deliveries(status, next_attempt_at);
