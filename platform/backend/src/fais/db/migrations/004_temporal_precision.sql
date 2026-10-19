ALTER TABLE matches ADD COLUMN kickoff_date TEXT;
ALTER TABLE matches ADD COLUMN kickoff_timezone TEXT;
ALTER TABLE matches ADD COLUMN kickoff_precision TEXT NOT NULL DEFAULT 'UNKNOWN'
    CHECK(kickoff_precision IN ('MINUTE', 'DATE', 'UNKNOWN'));
ALTER TABLE matches ADD COLUMN kickoff_year_inferred INTEGER NOT NULL DEFAULT 0
    CHECK(kickoff_year_inferred IN (0, 1));

CREATE INDEX idx_matches_competition_date
ON matches(competition_id, kickoff_date, id);
