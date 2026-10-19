CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    before_payload TEXT CHECK(before_payload IS NULL OR json_valid(before_payload)),
    after_payload TEXT CHECK(after_payload IS NULL OR json_valid(after_payload)),
    remote_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC, id DESC);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);

CREATE TABLE alert_channels (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    channel_type TEXT NOT NULL CHECK(channel_type IN ('WEBHOOK')),
    webhook_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE scraper_sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    country_slug TEXT NOT NULL,
    competition_slug TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE admin_uploads (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    upload_type TEXT NOT NULL CHECK(upload_type IN ('JSON', 'SQLITE')),
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('STAGED', 'QUEUED', 'SUCCEEDED', 'FAILED')),
    job_id TEXT REFERENCES jobs(id),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE model_reviews (
    id INTEGER PRIMARY KEY,
    model_version_id INTEGER NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
    reviewer_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decision TEXT NOT NULL CHECK(decision IN ('APPROVED', 'REJECTED')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_model_reviews_version ON model_reviews(model_version_id, created_at DESC);
