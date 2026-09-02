# AGENTS.md — Working Agreement for Cutlass

Read this before making changes. It captures how this repo is built and the
conventions every contribution (human or agent) must follow.

## Project pointers

- **What this is / where it's going:** [`docs/ROADMAP.md`](docs/ROADMAP.md) — vision, plan index, sequencing.
- **Active plan:** the highest-numbered plan in [`docs/plans/`](docs/plans/) marked as in-progress; each round of work executes exactly one plan doc.
- **Decisions:** ADRs in [`docs/adr/`](docs/adr/) — anything load-bearing (schema choices, framework adoptions) gets one before it's built.
- **Research:** [`docs/research/`](docs/research/) — competitive landscape and technical background, with sources.

## Quality bar (enforced by CI, `.github/workflows/ci.yml`)

Every commit must keep all of these green — run them before committing:

```bash
cd backend   && ruff check . && ruff format --check . && mypy app && python -m pytest
cd frontend  && npm run lint && npm run typecheck && npm run test && npm run build
```

- Backend: Python 3.11+, FastAPI, ruff (lint+format), mypy **strict** on `app/`, pytest (needs ffmpeg on PATH; skips cleanly without).
- Frontend: React + **strict TypeScript**, ESLint, Prettier, Vitest.
- Dependencies: edit `requirements*.txt` inputs, then regenerate the
  `requirements*.lock` universal locks (command in README) — CI and Docker
  install from the locks.
- `DRY_RUN=1` stubs all model calls — tests never need an API key or network.

## Commit discipline (user preference — not optional)

**Bite-sized, easily digestible commits.** The git history is a review
interface and a roll-back mechanism; optimize for both.

1. **One purpose per commit.** A single refactor, a single fix, a single
   config addition. If the description needs "and", it's two commits.
2. **Every commit is green** on its own: lint, types, and tests pass at each
   commit in the stack. Never bury a fix inside an unrelated change —
   bisect/rollback depends on this.
3. **Stack when a feature needs several commits.** Order a stack so each
   commit builds on the previous one and remains shippable (e.g. behavior fix
   → mechanical migration → tooling that enforces it).
4. **Message format:** `type(scope): summary` in the imperative (types:
   `feat`, `fix`, `refactor`, `build`, `ci`, `test`, `docs`, `chore`), plus a
   body explaining *why* when it isn't obvious from the diff. No filler.
5. **Documentation ships with the change, not after:** user-facing behavior →
   README; architecture/plans → `docs/`; decisions → new ADR.
6. **Never commit** secrets (`.env` is gitignored and a test enforces it),
   build output (`dist/`), or local session artifacts (`.zcode/`).

## Workflow

- Work happens in stacked bite-sized commits on a branch, merged via PR once
  branch protection is on (see README "Presubmit").
- Plan docs are updated in the same commit that lands the work (status field:
  planned → in-progress → implemented).
- When exploring next steps, read the roadmap first; don't re-litigate
  decided ADRs — write a new ADR if a decision needs revisiting.
