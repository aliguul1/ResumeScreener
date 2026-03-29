-- AI Resume Screener — SQLite Schema
-- Run: sqlite3 screener.db < schema.sql

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL,
    requirements TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    applicant_name  TEXT    NOT NULL,
    applicant_email TEXT    NOT NULL,
    resume_text     TEXT,                       -- extracted from PDF
    filter_status   TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(filter_status IN ('pending', 'accepted', 'rejected')),
    ai_feedback     TEXT,                       -- optional: reasoning from AI
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status  ON applications(filter_status);

-- Trigger: keep updated_at current on jobs
CREATE TRIGGER IF NOT EXISTS jobs_updated_at
    AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Trigger: keep updated_at current on applications
CREATE TRIGGER IF NOT EXISTS applications_updated_at
    AFTER UPDATE ON applications
BEGIN
    UPDATE applications SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
