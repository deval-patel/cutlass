# ADR 0002: OTIO-inspired timeline JSON as the canonical edit format

- **Status:** Proposed (to be finalized at the start of Plan 1)
- **Date:** 2026-09-02
- **Deciders:** maintainer + agent

## Context

Today's "EDL" is a flat list of `{start_s, end_s, reason, confidence}` segments. The editor (Plan 3) and timeline-aware styles (Plan 4) need tracks, clips with source in/out points, A/V-linked edges, and later transitions/text/speed. We must pick the canonical internal representation before building on it. Relevant prior art: OpenTimelineIO (OTIO) is the film-industry interchange model behind Eddie AI's export matrix; EDL and FCPXML are what NLEs actually import.

## Decision (proposed)

The canonical internal format is a **versioned JSON document shaped after OTIO concepts** — `Timeline → Stack → Track (V1, A1, …) → Clip {asset_id, source_in, source_out, record_range}` with rational frame time internally and seconds at API boundaries. Full **OTIO the library** is adopted at the edges (import/export adapters) rather than as the storage format, so:

- storage stays plain JSON (inspectable, diffable, portable to any client);
- OTIO gives us FCPXML/EDL/Premiere-XML conversion for free at export time without coupling the data model to it;
- we can carry cutlass-specific metadata (reason, confidence, style provenance) that OTIO would force into metadata bags.

## Alternatives considered

1. **Store OTIO XML/serialized form directly** — maximal interop, but opaque diffs, heavier client parsing, and metadata-bag sprawl for our analysis annotations.
2. **Stay flat-segments + parallel structures** — rejected: every Plan 3/4 feature would grow another side-list; one document model is the point.
3. **Adopt a web-editor format (e.g. a JS editor's schema)** — rejected: ties the product to a UI library we're explicitly not adopting (in-house timeline, Plan 3).

## Consequences

- `+` Diffable, versionable documents; clean human review in PRs.
- `+` Free NLE interchange via OTIO adapters when export lands (Plan 3).
- `−` We own a schema and a mapping layer to OTIO; must keep round-trip tests honest.
- Migration: existing segment lists convert 1:1 into single-track timelines (Plan 1 task).
