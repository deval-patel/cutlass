# ADR 0001: TypeScript for the frontend

- **Status:** Accepted (implemented as part of Plan 0)
- **Date:** 2026-09-02
- **Deciders:** maintainer + agent

## Context

The frontend is about to grow from two components into a real editor codebase (timeline store, command/undo stack, API client, feature modules). It was plain JSX with no type information anywhere; API payload shapes were implicit and drifted silently (e.g. `segments` is an int in the job-list response but an array in the job-detail response — nothing catches that today).

## Decision

Adopt **TypeScript in strict mode** for all frontend source (`strict: true`, no `any` unless locally justified and commented). Type checking runs in CI and pre-commit alongside ESLint; API types are hand-written now and will be generated from the backend's OpenAPI schema in Plan 1.

## Consequences

- `+` Refactor safety for the editor work (the undo/command stack and timeline invariants need real types).
- `+` API shape mismatches become compile errors.
- `−` Slightly more ceremony for small components; mitigated by inference and colocated types.
- Types live close to their feature (`features/.../types.ts` from Plan 1 on); no global `types.ts` dumping ground.
