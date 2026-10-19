CREATE TABLE feed_files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')),
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_written INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_feed_files_status_processed
ON feed_files(status, processed_at);
