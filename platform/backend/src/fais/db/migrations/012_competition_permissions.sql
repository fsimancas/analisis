CREATE TABLE user_competition_permissions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, competition_id)
) STRICT;

CREATE INDEX idx_user_competition_permissions_user
ON user_competition_permissions(user_id, competition_id);

CREATE INDEX idx_user_competition_permissions_competition
ON user_competition_permissions(competition_id, user_id);
