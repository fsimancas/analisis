CREATE TABLE model_versions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    version TEXT NOT NULL,
    artifact_uri TEXT,
    feature_version TEXT NOT NULL,
    training_cutoff_utc TEXT,
    metrics TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metrics)),
    active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
) STRICT;

CREATE UNIQUE INDEX idx_one_active_model
ON model_versions(name) WHERE active = 1;

CREATE TABLE backtest_runs (
    id TEXT PRIMARY KEY,
    model_version_id INTEGER NOT NULL REFERENCES model_versions(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    cutoff_start_utc TEXT NOT NULL,
    cutoff_end_utc TEXT NOT NULL,
    metrics TEXT CHECK(metrics IS NULL OR json_valid(metrics)),
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    error TEXT
) STRICT;

INSERT INTO model_versions(
    name, algorithm, version, feature_version, metrics, active
) VALUES (
    'match-outcome', 'regularized-poisson', 'regularized-poisson-v1', 'team-goals-v1',
    '{"role":"auditable-baseline"}', 1
);
