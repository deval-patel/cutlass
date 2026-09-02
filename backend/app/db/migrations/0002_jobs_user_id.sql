-- Nullable owner column, designed in now so multi-user support can land
-- later without a rewrite (single-user today; always NULL).
ALTER TABLE jobs ADD COLUMN user_id TEXT;
