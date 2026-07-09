-- 0001_initial.sql — core tables from PROJECT_SPEC.md.
-- person and outreach are schema-only in Phase 1 (no logic touches them).

CREATE TABLE company (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    website     TEXT,
    notes       TEXT,
    is_target   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Case-insensitive uniqueness on company name.
CREATE UNIQUE INDEX idx_company_name ON company (name COLLATE NOCASE);

CREATE TABLE job (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES company(id),
    title               TEXT NOT NULL,
    location            TEXT,
    remote_type         TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (remote_type IN ('onsite', 'hybrid', 'remote', 'unknown')),
    source              TEXT NOT NULL,
    source_url          TEXT NOT NULL,
    description_text    TEXT NOT NULL,          -- raw pasted JD, stored verbatim
    posted_at           TEXT,
    discovered_at       TEXT NOT NULL DEFAULT (datetime('now')),
    dedup_hash          TEXT NOT NULL UNIQUE,
    relevance_score     INTEGER CHECK (relevance_score BETWEEN 0 AND 100),
    relevance_rationale TEXT,
    status              TEXT NOT NULL DEFAULT 'discovered'
                        CHECK (status IN ('discovered', 'ranked', 'shortlisted',
                                          'materials_ready', 'applied', 'in_process',
                                          'interview', 'offer', 'rejected', 'dropped')),
    status_updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_job_status ON job (status);
CREATE INDEX idx_job_source_url ON job (source_url);

CREATE TABLE generated_asset (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL REFERENCES job(id),
    kind                TEXT NOT NULL
                        CHECK (kind IN ('cv_bullets', 'cover_letter', 'form_answer')),
    prompt_context_hash TEXT NOT NULL,
    content             TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    my_edits            TEXT
);

-- Schema-only in Phase 1: future phases (HR contact finder, outreach) slot in here.
CREATE TABLE person (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER REFERENCES company(id),
    name        TEXT NOT NULL,
    role        TEXT,
    email       TEXT,
    linkedin_url TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE outreach (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES person(id),
    job_id      INTEGER REFERENCES job(id),
    kind        TEXT NOT NULL,       -- e.g. cold_email, referral_request
    status      TEXT NOT NULL DEFAULT 'draft',
    content     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
