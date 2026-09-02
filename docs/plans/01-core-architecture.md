# Plan 1 — Core Architecture for Scale

**Status: in-progress (started Sept 2026).** Prerequisite for the editor (Plan 3) and style-v2 (Plan 4); strongly recommended before Plan 2's API surface grows. Task 1 uses the migration approach recorded in ADR-0003.

## Goal

Restructure the app from "one upload = one job = one flat segment list" into a **Project → Asset → Timeline** model with a layered backend and a frontend that can host a large editor codebase. This is the plan that makes the next 10k lines of code pleasant instead of a rewrite.

## Design

### Domain model
- **Project** — the unit of work ("Japan trip vlog"). Owns assets, one timeline, drafts/style metadata. `user_id TEXT NULL` column from day one (multi-user-ready, per ADR-0003 pending).
- **Asset** — an ingested source file (today's "job" becomes ingest-of-one-asset): probe metadata, frames manifest, frame notes, transcript, audio peaks. Analysis artifacts attach to the *asset* (they describe the source, not any edit).
- **Timeline** — a versioned JSON document in OTIO-inspired shape (see ADR-0002): tracks (V1/A1, extensible), clips referencing `{asset_id, source_in_s, source_out_s}`, record frame rate; later: transitions, text, speed effects. Autosave + named versions (draft history).
- The current flat segment EDL is represented as a *simple timeline*: one track, clips from one asset, gaps removed. A compatibility migration converts existing jobs.

### Backend layering (routers → services → repositories)
- `repositories/` — all SQL behind interfaces (JobsRepo → AssetsRepo/ProjectsRepo/TimelinesRepo). No SQL outside the layer; makes the future Postgres/auth swap mechanical.
- `services/` — pipeline orchestration, analysis, rendering, timeline validation.
- `routers/` — HTTP concerns only (parse, authorize-later, delegate, shape responses).
- **Migrations**: Alembic against SQLite (versioned, CI-checked); replaces try/except `ALTER TABLE`.
- **SQLite pragmas**: WAL + busy_timeout everywhere (concurrent job writes).
- **Job execution**: table-backed in-process worker pool (`jobs`/`tasks` table + N worker threads) replacing `BackgroundTasks` — survives restarts (pending jobs resume), bounds concurrent ffmpeg/LLM work. Celery stays out until multi-process deploys exist.
- **Progress**: SSE endpoint per project/asset (polling fallback kept); replaces the 2s poll-and-pray loop.
- **API**: `/api/v1/...` prefix, consistent error envelope, pagination on list endpoints, ETag/Cache-Control on media, proper 409/422 semantics preserved.
- **Storage lifecycle**: delete project/asset endpoints that remove DB rows + artifacts; optional retention GC for orphaned temp audio (today's leak: `uploads/<job>/audio/*.wav` is never cleaned).

### Frontend architecture
- Feature-folder structure: `features/projects`, `features/assets`, `features/editor`, `features/style` (components, hooks, api per feature).
- React Router — every project/job gets a URL (today a refresh loses your place).
- TanStack Query for server state; Zustand store for editor state (timeline, selection, undo stack) — kept separate on purpose.
- Typed API client generated from FastAPI's OpenAPI schema (`openapi-typescript`), refreshed in CI or pre-commit.
- Extract a `<MediaPlayer>` with cut-aware playback from JobView (it becomes the editor's source/program monitor).

## Task breakdown (order matters)

1. Alembic bootstrap + migrate existing `jobs` table; add `user_id` nullable everywhere it will be needed.
2. Repository layer extraction; move all SQL out of `storage.py`; WAL pragmas; keep API behavior identical (tests stay green throughout).
3. Job queue: tasks table + worker threads; SSE progress endpoint; frontend swaps polling for SSE (keep polling fallback).
4. Project/Asset/Timeline models + CRUD API `/api/v1`; compatibility shim keeps `/api/*` endpoints working during migration; data migration for existing jobs.
5. Timeline JSON schema (OTIO-shaped) + validator + round-trip tests.
6. Frontend restructure: router, TanStack Query, feature folders, generated client; JobView becomes `features/projects/ProjectView` + shared `MediaPlayer`.
7. Storage lifecycle: delete endpoints, artifact GC, temp-audio cleanup.

## Acceptance criteria

- Existing user flows (upload → draft → edit → render → download) work unchanged through the new API.
- Timelines are versioned; editing a timeline never loses history; render + preview consume the timeline document.
- Killing the server mid-analysis leaves jobs in a resumable state (re-run pending on start).
- No SQL outside repositories; no inline fetch logic in components; CI enforces types/lint/tests.
- Multiple concurrent uploads don't produce `database is locked`.

## Non-goals

Auth implementation (seams only), Postgres, Celery/Redis, the timeline *editor UI* (Plan 3), style control (Plan 2).
