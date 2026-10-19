CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'USER' CHECK(role IN ('USER', 'ANALYST', 'ADMIN')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE favorites (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK((match_id IS NOT NULL) <> (team_id IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX idx_favorite_match
ON favorites(user_id, match_id) WHERE match_id IS NOT NULL;
CREATE UNIQUE INDEX idx_favorite_team
ON favorites(user_id, team_id) WHERE team_id IS NOT NULL;

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'KICKOFF', 'GOAL', 'FULL_TIME', 'PREDICTION_READY', 'ODDS_MOVEMENT'
    )),
    threshold REAL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, match_id, event_type)
) STRICT;

CREATE INDEX idx_alerts_active_match ON alerts(active, match_id);
