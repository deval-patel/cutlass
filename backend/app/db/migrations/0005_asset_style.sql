-- Plan 2: style selection rides on the asset — set at upload time or by a
-- re-draft request; the pipeline reads it from here (the queue carries only
-- asset ids, so style changes are durable across restarts).
ALTER TABLE assets ADD COLUMN style_preset TEXT;
ALTER TABLE assets ADD COLUMN user_brief TEXT;
