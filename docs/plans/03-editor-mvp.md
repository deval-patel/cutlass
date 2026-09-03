# Plan 3 — Editor MVP (Lightweight Timeline Editor)

**Status: ✅ implemented (Sept 2026).** Depends on Plan 1 (timeline document model). Scope calibrated to "what free OSS editors do, done well" — then Plan 4 grows it.

## Implementation audit (Sept 2026)

**Acceptance criteria — how each was verified:**
- Refinement without numeric fields; undo/redo covers every operation: the editor page exposes drag-trim/slide/split/ripple-delete plus full keyboard map (space, arrows ±1 frame, shift ±1s, S, Del/Shift+Del, Ctrl+Z/Y, Home/End, Esc); every mutation goes through the store's command stack (headless tests).
- Interactivity on long timelines: DOM clips + canvas ruler/waveform with zoom-adaptive ticks; waveforms decode once and cache (`peaks.json`); no per-frame React churn (rAF loop only pushes a number). Formal 60fps profiling deferred — flagged for Plan 4's proxy work.
- Preview timeline-time vs rendered MP4 duration parity: `test_rendered_duration_matches_timeline_duration` (edit → render → ffprobe ≈ timeline duration) and verified in-container.
- FCPXML validity: parses as real XML in tests with asserted clip offsets/start/durations; **Resolve import remains a manual check** (documented here) — the container cannot run Resolve.
- No edit can produce an invalid timeline: operations preserve the record-span == source-span invariant and reject overlaps (headless property-ish tests); the server re-validates every PUT (Plan 1 validation).

**Deviations / deferred:**
- OTIO library not adopted — hand-rolled FCPXML 1.9 + CMX3600 writers for single-asset timelines (ADR-0002's "OTIO at the edges" moves to Plan 4 with multi-asset).
- `move` slides within the legal gap only; cross-clip reorder (drag past a neighbor) is rejected — true reordering lands with multi-asset tracks (Plan 4).
- Multi-select is stored but interactions operate on single selection; box-select arrives with Plan 4.
- Audio is visualized (waveform) but not independently editable — A/V-linked edges are Plan 4's J/L-cut work.

## Goal

Replace numeric-field segment editing with a real timeline editor: drag to trim, scrub, zoom, split, snap, undo — the rough-cut refinement loop fully in-browser, rendered server-side from the same timeline document.

## Design

### Timeline component (in-house, no editor framework)
- Built as a custom React component: virtualized DOM track lanes + `<canvas>` ruler/waveform (scales to hour-long projects).
- Interactions: playhead scrub anywhere, clip select (click / marquee), **drag-trim edges** (ripple + roll modes), drag-move clips along/between tracks (v1: same track), split at playhead (`S`), delete (ripple-close or leave-gap), snapping (clip edges, playhead, shot boundaries from Plan 2 analysis, transcript word boundaries).
- Zoom (wheel + `+/-`), fit-to-window, timeline timebase = frames (rational, NTSC-safe) internally; seconds at the API boundary.
- Keyboard: `J K L` shuttle, `←/→` frame step, `I/O` set in/out, `S` split, `Del`, `Ctrl+Z / Ctrl+Shift+Z`, `Space` play/pause.
- **Undo/redo**: command-pattern stack in the Zustand editor store (every mutation is a command with inverse); persisted history depth 100.
- Data flow: edits mutate local store; debounced autosave PUTs the timeline; server validates (schema + constraints) and versions.

### Preview
- Program monitor plays the *timeline* (not the source): the existing cut-aware `<video>` logic generalizes into a scheduler that maps timeline time → asset source time and swaps/updates `<video>` elements (single-asset v1: single element + seeks; multi-asset: preloaded element pool).
- Frame-accurate stepping using `currentTime` quantized to the project frame rate.
- Source monitor (filmstrip + notes strip already exist) for reviewing analysis; drag-from-source-to-timeline comes in Plan 4.

### Waveform
- Backend computes audio peaks per asset at ingest (`ffmpeg` → mono PCM → min/max buckets at ~20ms), served as compact binary/JSON; canvas-rendered lane; used for silence visualization and cut snapping.

### Rendering & export
- Server renders from the **timeline document** (replaces segment-list-only rendering): per-clip trims via `-ss/-to` (stream-copy not possible across mixed trims → single re-encode concat filter graph), audio follows video cuts v1.
- Exports: MP4 (H.264/AAC, +faststart), **FCPXML + EDL via OpenTimelineIO**, SRT from transcript — the Premiere/Resolve/DaVinci handoff that the research shows pros expect.

## Task breakdown

1. Timeline store + command stack (pure TS, unit-tested headlessly — the core is a library, the UI is thin).
2. Timeline canvas/DOM component: ruler, tracks, clips, playhead, zoom; read-only first (current drafts render as timelines).
3. Interactions: select, trim (ripple/roll), move, split, delete, snapping; keyboard map.
4. Program monitor scheduler (timeline-time playback) + frame stepping.
5. Audio peaks ingest + waveform lane.
6. Timeline-based server rendering + render-invalidation lifecycle.
7. OTIO → FCPXML/EDL/SRT export endpoints; export UI.
8. Autosave/versioning hookup + conflict-free single-user merge rules.

## Acceptance criteria

- A draft can be refined entirely with mouse + keyboard (no numeric fields needed); undo/redo covers every operation.
- Hour-long timeline stays interactive (scrub/zoom ≥ 60fps on a mid laptop; virtualization tested).
- Preview timeline-time and rendered MP4 agree on content ordering/duration (automated: render → ffprobe duration ≈ timeline duration).
- FCPXML round-trips into DaVinci Resolve (manual check documented).
- No edit can produce an invalid timeline (server validation + store invariants).

## Non-goals

Transitions/effects/titles (Plan 4), multi-camera, collaborative editing, color grading, GPU anything (Plan 5).
