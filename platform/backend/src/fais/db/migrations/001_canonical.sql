CREATE TABLE source_providers (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    base_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE countries (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    provider_payload TEXT CHECK(provider_payload IS NULL OR json_valid(provider_payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE competitions (
    id INTEGER PRIMARY KEY,
    country_id INTEGER REFERENCES countries(id),
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    sport TEXT NOT NULL DEFAULT 'football',
    gender TEXT,
    tier TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, slug)
) STRICT;

CREATE TABLE competition_provider_refs (
    competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    external_id TEXT NOT NULL,
    external_name TEXT,
    url TEXT,
    metadata TEXT CHECK(metadata IS NULL OR json_valid(metadata)),
    PRIMARY KEY(provider_id, external_id),
    UNIQUE(competition_id, provider_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE seasons (
    id INTEGER PRIMARY KEY,
    competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    starts_at TEXT,
    ends_at TEXT,
    UNIQUE(competition_id, name)
) STRICT;

CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    country_id INTEGER REFERENCES countries(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, normalized_name)
) STRICT;

CREATE TABLE team_provider_refs (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    external_id TEXT NOT NULL,
    external_name TEXT,
    PRIMARY KEY(provider_id, external_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE team_aliases (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    provider_id INTEGER REFERENCES source_providers(id),
    country_id INTEGER REFERENCES countries(id),
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    UNIQUE(provider_id, country_id, normalized_alias)
) STRICT;

CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    competition_id INTEGER NOT NULL REFERENCES competitions(id),
    season_id INTEGER REFERENCES seasons(id),
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    kickoff_utc TEXT,
    kickoff_raw TEXT,
    round_name TEXT,
    status TEXT NOT NULL CHECK(status IN (
        'SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', 'SUSPENDED', 'CANCELLED', 'UNKNOWN'
    )),
    match_type TEXT NOT NULL CHECK(match_type IN ('RESULT', 'UPCOMING')),
    home_score INTEGER CHECK(home_score IS NULL OR home_score >= 0),
    away_score INTEGER CHECK(away_score IS NULL OR away_score >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(home_team_id <> away_team_id),
    CHECK((home_score IS NULL) = (away_score IS NULL))
) STRICT;

CREATE INDEX idx_matches_competition_kickoff ON matches(competition_id, kickoff_utc);
CREATE INDEX idx_matches_home_kickoff ON matches(home_team_id, kickoff_utc);
CREATE INDEX idx_matches_away_kickoff ON matches(away_team_id, kickoff_utc);
CREATE INDEX idx_matches_status ON matches(status);

CREATE TABLE match_provider_refs (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    external_id TEXT NOT NULL,
    url TEXT,
    raw_hash TEXT,
    fetched_at TEXT,
    PRIMARY KEY(provider_id, external_id),
    UNIQUE(match_id, provider_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE odds_snapshots (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    market_key TEXT NOT NULL,
    selection_key TEXT NOT NULL,
    line REAL,
    decimal_odd REAL NOT NULL CHECK(decimal_odd > 1.0),
    captured_at TEXT NOT NULL,
    raw_payload TEXT CHECK(raw_payload IS NULL OR json_valid(raw_payload)),
    UNIQUE(match_id, provider_id, market_key, selection_key, line, captured_at)
) STRICT;

CREATE INDEX idx_odds_match_time ON odds_snapshots(match_id, captured_at DESC);

CREATE TABLE ingestion_runs (
    id INTEGER PRIMARY KEY,
    provider_id INTEGER REFERENCES source_providers(id),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    started_at TEXT,
    finished_at TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_written INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    metadata TEXT CHECK(metadata IS NULL OR json_valid(metadata)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE data_quality_issues (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    source_provider_id INTEGER REFERENCES source_providers(id),
    severity TEXT NOT NULL CHECK(severity IN ('PASS', 'WARNING', 'FAIL', 'QUARANTINED')),
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT CHECK(context IS NULL OR json_valid(context)),
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
) STRICT;

CREATE INDEX idx_quality_open ON data_quality_issues(severity, resolved_at);
CREATE UNIQUE INDEX idx_quality_identity
    ON data_quality_issues(entity_type, entity_id, source_provider_id, code);

CREATE TABLE feature_snapshots (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    cutoff_utc TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    input_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, team_id, cutoff_utc, feature_version)
) STRICT;

CREATE TABLE predictions (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    cutoff_utc TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('READY', 'STALE', 'ERROR')),
    home_lambda REAL NOT NULL CHECK(home_lambda > 0),
    away_lambda REAL NOT NULL CHECK(away_lambda > 0),
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    input_hash TEXT NOT NULL,
    random_seed INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, cutoff_utc, model_version, feature_version, input_hash)
) STRICT;

CREATE INDEX idx_predictions_match_created ON predictions(match_id, created_at DESC);

INSERT INTO source_providers(code, name, base_url) VALUES
    ('legacy_flashscore', 'Legacy Flashscore', 'https://www.flashscore.co'),
    ('fotmob', 'FotMob', 'https://www.fotmob.com'),
    ('betplay', 'BetPlay', 'https://betplay.com.co');
