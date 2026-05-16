-- Run this in the Supabase SQL Editor to set up the multi-project schema.
-- Supabase auth.users is managed by Supabase Auth — no need to create it.

-- ── Projects ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS projects (
    id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID        NOT NULL,
    name        TEXT        NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS projects_user_id_idx ON projects(user_id);

-- ── Requirements ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS requirements (
    id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id          UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id             UUID        NOT NULL,
    content             TEXT        NOT NULL,
    input_type          TEXT        DEFAULT 'plain_text',
    project_context     TEXT,
    tech_stack          TEXT,
    additional_context  TEXT,
    github_repo_url     TEXT,
    website_url         TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS requirements_project_id_idx ON requirements(project_id);

-- ── Test Suites ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS test_suites (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id       UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id   UUID        REFERENCES requirements(id) ON DELETE SET NULL,
    user_id          UUID        NOT NULL,
    feature_name     TEXT,
    total_test_cases INT         DEFAULT 0,
    quality_score    FLOAT       DEFAULT 0.0,
    manual_output    TEXT,
    api_output       TEXT,
    ui_output        TEXT,
    markdown_output  TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS test_suites_project_id_idx ON test_suites(project_id);
CREATE INDEX IF NOT EXISTS test_suites_requirement_id_idx ON test_suites(requirement_id);

-- ── Execution Logs ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS execution_logs (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id       UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    test_suite_id    UUID        REFERENCES test_suites(id) ON DELETE SET NULL,
    requirement_id   UUID        REFERENCES requirements(id) ON DELETE SET NULL,
    user_id          UUID        NOT NULL,
    job_id           TEXT,
    status           TEXT        NOT NULL,   -- 'running' | 'completed' | 'failed'
    feature_name     TEXT,
    total_test_cases INT         DEFAULT 0,
    quality_score    FLOAT       DEFAULT 0.0,
    error_message    TEXT,
    started_at       TIMESTAMPTZ DEFAULT NOW(),
    completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS execution_logs_project_id_idx ON execution_logs(project_id);
CREATE INDEX IF NOT EXISTS execution_logs_status_idx     ON execution_logs(status);

-- ── updated_at trigger for projects ──────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
