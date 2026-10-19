ALTER TABLE seasons ADD COLUMN assignment_method TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE seasons ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0
    CHECK(confidence >= 0.0 AND confidence <= 1.0);

CREATE INDEX idx_seasons_competition_dates
ON seasons(competition_id, starts_at, ends_at);
