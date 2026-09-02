-- Baseline schema: exactly what the app created before the migration
-- runner existed. Legacy databases are stamped with this version and
-- never re-run it; fresh databases apply it as the first migration.
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    meta TEXT,
    segments TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    progress TEXT,
    notes TEXT,
    transcript TEXT
);
