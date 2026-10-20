CREATE TABLE analyst_workbooks (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_analyst_workbooks_user
ON analyst_workbooks(user_id, updated_at DESC);

CREATE TABLE analysis_runs (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL CHECK(analysis_type IN ('PREDICTION', 'MONTE_CARLO', 'ODDS_VALUE')),
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    parameters TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(parameters)),
    result TEXT CHECK(result IS NULL OR json_valid(result)),
    model_version TEXT,
    random_seed INTEGER,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
) STRICT;

CREATE INDEX idx_analysis_runs_match_created
ON analysis_runs(match_id, created_at DESC);

ALTER TABLE scraper_sources ADD COLUMN provider_code TEXT NOT NULL DEFAULT 'flashscore'
    CHECK(provider_code IN ('flashscore', 'fotmob', 'betplay'));

ALTER TABLE scraper_sources ADD COLUMN ingestion_kind TEXT NOT NULL DEFAULT 'MATCHES'
    CHECK(ingestion_kind IN ('MATCHES', 'ODDS', 'DETAILS'));
