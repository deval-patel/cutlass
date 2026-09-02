-- Cutover: every job becomes the single asset of its own project (named
-- after its file). Asset ids are preserved, so legacy /api/jobs/{id} URLs
-- keep working. Draft timelines are seeded lazily by the application when
-- first read (it needs the asset's fps to build the document).
BEGIN;
INSERT INTO projects (id, name, user_id, created_at)
SELECT 'p-' || id, filename, user_id, created_at FROM jobs;

INSERT INTO assets (
    id, project_id, filename, status, error, meta, segments,
    notes, transcript, progress, user_id, created_at
)
SELECT
    id, 'p-' || id, filename, status, error, meta, segments,
    notes, transcript, progress, user_id, created_at
FROM jobs;

DROP TABLE jobs;
COMMIT;
