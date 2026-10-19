CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    title TEXT NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT,
    UNIQUE(alert_id, event_key)
) STRICT;

CREATE INDEX idx_notifications_user_unread
ON notifications(user_id, read_at, created_at DESC);
