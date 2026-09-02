# ADR 0003: Lightweight ordered SQL migrations over Alembic

- **Status:** Accepted
- **Date:** 2026-09-02
- **Deciders:** maintainer + agent
- **Supersedes:** the "Alembic" mention in `docs/plans/01-core-architecture.md` task 1 (this ADR records the final choice).

## Context

Plan 1 replaces the ad-hoc `ALTER TABLE` try/except loop in `storage.init_db()` with real versioned migrations. Alembic is the default answer in the Python ecosystem, but it is built around SQLAlchemy engines and metadata; this backend deliberately uses **raw `sqlite3`** with Pydantic models and no ORM anywhere.

## Decision

Ship a small in-repo migration runner (`backend/app/db/migrations.py`):

- ordered `NNNN_name.sql` files under `backend/app/db/migrations/`, applied in filename order;
- a `schema_migrations(version, applied_at)` table records applied versions;
- databases created before the runner existed (a `jobs` table with no migration history) are **stamped** with the baseline version and then upgraded normally;
- migrations run at app startup; applying is idempotent (re-running is a no-op).

## Alternatives considered

1. **Alembic** — industry standard, but drags in the SQLAlchemy dependency tree to manage four tables of raw SQL we would never autogenerate from models. Revisit via a new ADR if the schema becomes relational enough to need autogenerate or the project moves off SQLite.
2. **Keep the ALTER loop** — rejected: unversioned, can't express destructive changes, and every future column is another try/except.

## Consequences

- `+` Zero new dependencies; ~70 lines; trivially testable (fresh DB, legacy DB, idempotency — all in `tests/test_migrations.py`).
- `+` SQL lives in reviewable files; history is inspectable with plain SQL.
- `−` We own the runner: no down-migrations, no branching semantics. Acceptable at this schema size; destructive changes are handled by writing forward migrations carefully.
