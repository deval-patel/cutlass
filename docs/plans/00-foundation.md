# Plan 0 — Engineering Foundation

**Status: ✅ implemented (Sept 2026).** This document describes what was put in place and serves as the reference for the quality bar going forward.

## Goal

Make the repository enforce its own quality: linting, formatting, type checking, and tests on both stacks, running automatically on every PR and locally on every commit. No slop by construction — CI is the gate, not reviewer stamina.

## What was implemented

### Backend (Python)
- `backend/pyproject.toml` — tool config: **ruff** (lint + formatter), **mypy** (strict on `app/`, relaxed on `tests/`), pytest config.
- Dependency policy: `requirements.txt` / `requirements-dev.txt` are human-edited inputs; `requirements.lock` / `requirements-dev.lock` are pinned **universal (cross-platform) locks** generated with `uv pip compile --universal` — CI and Docker install from the locks. Dev tooling (pytest, ruff, mypy, pytest-cov) lives in `requirements-dev.*` only.
- `GET /api/health` liveness endpoint (used by the Docker `HEALTHCHECK`).
- Test-suite robustness fix: missing ffmpeg now skips cleanly via a `pytest_collection_modifyitems` hook (module-level `pytestmark` in conftest.py never propagated to test modules — missing ffmpeg used to produce 14 setup errors instead of skips).

### Frontend (TypeScript)
- Full migration of the JSX sources to **strict TypeScript** (`src/*.tsx`, `tsconfig.json` with `strict: true`).
- **ESLint 9** flat config (typescript-eslint, react-hooks) + **Prettier**; `.prettierrc` matched to the codebase's existing style (no semicolons, single quotes).
- **Vitest + Testing Library** with jsdom; initial suites for the upload flow and job polling; `lint`, `typecheck`, `test` npm scripts.

### CI & hooks
- `.github/workflows/ci.yml` — two jobs on every PR and push to `main`:
  - *backend*: Ubuntu (ffmpeg preinstalled) → ruff check, ruff format --check, mypy, pytest.
  - *frontend*: npm ci → eslint, tsc, vitest run, vite build.
- `.pre-commit-config.yaml` — ruff + prettier + hygiene hooks (trailing whitespace, EOF newlines, large files) for local commits.
- Branch protection must be enabled once in GitHub settings (see README "Presubmit" section) — CI workflows cannot configure it.

### Hygiene fixes surfaced by the new tooling
- `JobView.startRender` polling interval leaked on unmount; render-poll and status-poll now clean up properly and survive transient fetch failures instead of silently freezing.
- Segment-editor numeric inputs no longer push `NaN` into the PUT body.
- `App.refreshJobs` no longer leaves unhandled promise rejections on network errors.

### Docker hardening
- `npm ci` (was `npm install`) for reproducible frontend builds; non-root `app` user; `HEALTHCHECK` hitting `/api/health`.

## Verification

- `ruff check` + `ruff format --check` clean on `backend/`.
- `mypy app/` clean.
- `pytest` — all pre-existing tests green.
- `npm run lint && npm run typecheck && npm run test && npm run build` clean.
- `docker build` succeeds.

## Non-goals (deferred)

Code architecture changes (Plan 1), any prompt/model changes (Plan 2), frontend feature work.
