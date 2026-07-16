-- 0003_opportunity.sql — market-intelligence items surfaced by the
-- Opportunities scan (new startups, AI developments, learning gaps,
-- entrepreneurship angles). Separate from job/generated_asset: an
-- opportunity is not a job posting and never advances the job lifecycle.

CREATE TABLE opportunity (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT NOT NULL
                     CHECK (kind IN ('startup', 'ai_development', 'learning',
                                     'entrepreneurship')),
    title            TEXT NOT NULL,
    summary          TEXT NOT NULL,
    why_relevant     TEXT NOT NULL,
    source_url       TEXT,
    suggested_action TEXT,
    dedup_hash       TEXT NOT NULL UNIQUE,
    status           TEXT NOT NULL DEFAULT 'new'
                     CHECK (status IN ('new', 'saved', 'dismissed')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_opportunity_status ON opportunity (status);
