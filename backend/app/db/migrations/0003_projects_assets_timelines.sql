-- Plan 1 domain model: Project -> Assets -> Timeline (+ versions).
-- Additive only; the cutover migration (jobs -> assets) comes after the
-- code switches over, so this migration is safe to apply while the app
-- still runs on the jobs table.

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    user_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    meta TEXT,
    segments TEXT,
    notes TEXT,
    transcript TEXT,
    progress TEXT,
    user_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

CREATE TABLE IF NOT EXISTS timelines (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'main',
    document TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_timelines_project_name ON timelines(project_id, name);

CREATE TABLE IF NOT EXISTS timeline_versions (
    id TEXT PRIMARY KEY,
    timeline_id TEXT NOT NULL REFERENCES timelines(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    label TEXT,
    document TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(timeline_id, version)
);
