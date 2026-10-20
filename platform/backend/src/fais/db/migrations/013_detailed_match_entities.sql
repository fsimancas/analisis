CREATE TABLE players (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    country_id INTEGER REFERENCES countries(id),
    date_of_birth TEXT,
    primary_position TEXT,
    provider_payload TEXT CHECK(provider_payload IS NULL OR json_valid(provider_payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, normalized_name, date_of_birth)
) STRICT;

CREATE TABLE player_provider_refs (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    external_id TEXT NOT NULL,
    external_name TEXT,
    metadata TEXT CHECK(metadata IS NULL OR json_valid(metadata)),
    PRIMARY KEY(provider_id, external_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE referees (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    country_id INTEGER REFERENCES countries(id),
    category TEXT,
    provider_payload TEXT CHECK(provider_payload IS NULL OR json_valid(provider_payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, normalized_name)
) STRICT;

CREATE TABLE referee_provider_refs (
    referee_id INTEGER NOT NULL REFERENCES referees(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES source_providers(id),
    external_id TEXT NOT NULL,
    external_name TEXT,
    PRIMARY KEY(provider_id, external_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE team_squads (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    season_id INTEGER REFERENCES seasons(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    shirt_number INTEGER,
    position TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    starts_at TEXT,
    ends_at TEXT,
    UNIQUE(team_id, season_id, player_id)
) STRICT;

CREATE TABLE formations (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    shape TEXT NOT NULL CHECK(json_valid(shape))
) STRICT;

CREATE TABLE lineups (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('PROBABLE', 'CONFIRMED', 'FINAL')),
    formation_id INTEGER REFERENCES formations(id),
    source_provider_id INTEGER REFERENCES source_providers(id),
    submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    announced_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, team_id, status)
) STRICT;

CREATE TABLE lineup_players (
    id INTEGER PRIMARY KEY,
    lineup_id INTEGER NOT NULL REFERENCES lineups(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    shirt_number INTEGER,
    position_code TEXT,
    starter INTEGER NOT NULL DEFAULT 1 CHECK(starter IN (0, 1)),
    field_x REAL CHECK(field_x IS NULL OR (field_x >= 0 AND field_x <= 100)),
    field_y REAL CHECK(field_y IS NULL OR (field_y >= 0 AND field_y <= 100)),
    minute_on INTEGER,
    minute_off INTEGER,
    UNIQUE(lineup_id, player_id)
) STRICT;

CREATE TABLE match_referees (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    referee_id INTEGER NOT NULL REFERENCES referees(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'MAIN' CHECK(role IN ('MAIN', 'ASSISTANT', 'FOURTH', 'VAR', 'AVAR')),
    PRIMARY KEY(match_id, referee_id, role)
) STRICT, WITHOUT ROWID;

CREATE TABLE match_events (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    source_provider_id INTEGER REFERENCES source_providers(id),
    external_id TEXT,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'KICKOFF', 'GOAL', 'OWN_GOAL', 'PENALTY_GOAL', 'MISSED_PENALTY',
        'YELLOW_CARD', 'RED_CARD', 'SUBSTITUTION', 'VAR', 'HALF_TIME', 'FULL_TIME', 'OTHER'
    )),
    minute INTEGER CHECK(minute IS NULL OR minute >= 0),
    added_minute INTEGER CHECK(added_minute IS NULL OR added_minute >= 0),
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    related_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    payload TEXT CHECK(payload IS NULL OR json_valid(payload)),
    occurred_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_provider_id, external_id)
) STRICT;

CREATE INDEX idx_match_events_timeline
ON match_events(match_id, minute, added_minute, id);

CREATE TABLE team_match_statistics (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    period TEXT NOT NULL DEFAULT 'ALL',
    stat_key TEXT NOT NULL,
    stat_value REAL,
    raw_value TEXT,
    source_provider_id INTEGER REFERENCES source_providers(id),
    UNIQUE(match_id, team_id, period, stat_key, source_provider_id)
) STRICT;

CREATE TABLE player_match_statistics (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    stat_key TEXT NOT NULL,
    stat_value REAL,
    raw_value TEXT,
    source_provider_id INTEGER REFERENCES source_providers(id),
    UNIQUE(match_id, player_id, stat_key, source_provider_id)
) STRICT;

CREATE TABLE injuries (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    injury_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'RECOVERING', 'CLEARED')),
    starts_at TEXT,
    expected_return_at TEXT,
    source_provider_id INTEGER REFERENCES source_providers(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

INSERT INTO formations(code, name, shape) VALUES
    ('4-4-2', '4-4-2', '[[5,50],[25,15],[25,38],[25,62],[25,85],[55,15],[55,38],[55,62],[55,85],[82,35],[82,65]]'),
    ('4-3-3', '4-3-3', '[[5,50],[25,15],[25,38],[25,62],[25,85],[52,25],[52,50],[52,75],[82,18],[82,50],[82,82]]'),
    ('4-2-3-1', '4-2-3-1', '[[5,50],[25,15],[25,38],[25,62],[25,85],[48,35],[48,65],[68,20],[68,50],[68,80],[86,50]]'),
    ('3-5-2', '3-5-2', '[[5,50],[25,25],[25,50],[25,75],[52,8],[52,30],[52,50],[52,70],[52,92],[82,35],[82,65]]');
