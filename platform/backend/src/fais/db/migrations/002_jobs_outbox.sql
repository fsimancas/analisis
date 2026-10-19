CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    result TEXT CHECK(result IS NULL OR json_valid(result)),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT
) STRICT;

CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);

CREATE TABLE event_outbox (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL,
    event_key TEXT NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT,
    UNIQUE(topic, event_key)
) STRICT;

CREATE INDEX idx_outbox_unpublished ON event_outbox(published_at, id);
