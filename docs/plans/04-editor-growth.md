# Plan 4 — Editor Growth + Style v2

**Status: in-progress — phase 1 ✅ (multi-asset), phase 2 ✅ (transitions), Sept 2026; remaining features queued.** Depends on Plans 1–3. Feature-sized chunks, each independently shippable.

## Phase 2 audit: transitions (Sept 2026)

Crossfades between adjacent clips on a track, end to end:

- **Schema**: `clip.transition_out = {type, duration_s}` — a transition on
  the LEFT clip of a junction. Validation allows the resulting overlap
  exactly when it equals the transition duration and the duration fits
  inside both clips; every other overlap is still rejected.
- **Render**: clips group into runs joined by transitions; within a run the
  video chains through `xfade` (offset = junction record position relative
  to the run start) and audio chains through `acrossfade`; runs concat.
  Total duration = sum(spans) − sum(transition durations) — parity tested.
- **Exports**: FCPXML emits a `<transition>` resource + spine element per
  junction (XML-valid; NLE import remains the documented manual check).
  EDL marks junctions with a `* CROSSFADE` comment — full CMX3600 dissolve
  event pairs are deferred (lossy, documented).
- **Editor**: "crossfade" toggle on the selected clip's outgoing junction —
  adding shifts the next clip left to create the overlap (undoable);
  subsequent trims that break the overlap drop the transition (documented
  MVP semantics).

**Verified by**: schema validation tests (accept exact-D overlap, reject
mismatched/too-long/trailing), render integration tests (two 4s clips +
1s crossfade → 7s ffprobe-asserted output; mixed runs → 11s), export
tests (FCPXML transition resource/spine element, EDL junction comment),
store ops tests (shift-on-add, restore-on-remove, clamping, oracle);
Docker E2E renders a crossfade timeline through the API.

## Phase 1 audit: multi-asset timelines (Sept 2026)

The real travel use case — one project, many clips — is end-to-end:

- **Assembly**: each analyzed asset's draft auto-joins the project timeline (new assets append; re-drafted assets replace their own clips and move to the end — predictable, never overlapping).
- **Rendering**: one ffmpeg invocation with per-clip trims concatenated in record order across all inputs; duration parity holds for multi-asset timelines (service test: 5s from 3s+3s inputs; API test: two-asset project halve-and-close edit).
- **Exports**: FCPXML emits one resource per asset; CMX3600 events carry per-asset reel names (first 8 chars of the asset id, the field's width); SRT merges transcripts per asset.
- **Project redraft**: `POST /api/v1/projects/{id}/redraft` restyles every analyzed asset from cached analysis in one queued task (no vision calls); drafts re-assemble automatically; per-asset failures are isolated; crash recovery rides the existing redrafting→redraft map.
- **Editor**: asset browser (status, duration, style per asset) with one-click add-to-timeline (undoable), per-asset hue coding, cross-asset program monitor (src swap with pending seek), and the editor timeline reloads when a project redraft lands.

**Verified by**: 4 new backend test suites/cases + store tests; Docker E2E (two assets → project redraft → render parity → exports).

**Behavior note (documented, deliberate):** sentence-snapping (`cut_on: sentence`) aligns cut points to transcript-line boundaries within a 1.5s tolerance in BOTH directions — with coarse single-line transcripts (e.g. DRY_RUN) this can expand cuts to the line's edges. Word-level granularity (deferred, below) tightens this.

**Explicitly deferred to later Plan-4 phases** (in rough order): transitions (xfade), text/titles, music + ducking (audio tracks), caption burn-in, speed ramps (needs reworking the record-span ≡ source-span invariant — deliberately not rushed), basic color, B-roll insertion, proxies, J/L cuts + per-section pacing (style v2 timeline-aware knobs). The cross-asset JOINT selection (model choosing across all assets at once) is also deferred: phase 1 redrafts each asset independently and assembles.

## Goal

Grow the editor toward "daily-driver for one person making vlogs" and upgrade style control from flat segments to the full timeline.

## Editor features (rough priority order)

1. **Multi-asset timelines** — assemble the draft from *many* clips (the real travel use case: one project = one trip). Requires: asset browser, drag-to-timeline, per-asset analysis reuse, cross-asset AI draft generation (selection pass sees all assets' notes/transcripts).
2. **Transitions** — crossfade/dip-to-black between clips (render via xfade; UI: draggable transition handles at edit points).
3. **Text & titles** — text clips on the timeline (position/size/font/animation presets); rendered via drawtext/libass.
4. **Music + audio ducking** — music track, auto-duck under speech (sidechaincompress), level controls, fade handles.
5. **Captions** — burn-in captions from word-level transcript (styled presets: shorts-style pop captions), SRT/VTT export per timeline range.
6. **Speed ramps** — per-clip speed (setpts/atempo; curve editing UI later).
7. **Basic color** — brightness/contrast/saturation/temperature per clip (eq filter) — deliberately not Resolve.
8. **B-roll insertion** — AI suggests overlay candidates from other assets for the current A-roll segment ("this sentence mentions the temple → temple shot 3 exists"); one-click insert on V2.
9. **Proxy workflow** — generate low-res proxies at ingest for smooth scrubbing of 4K; swap to full-res at render.

## Style v2 (timeline-aware)

- **J/L cuts**: style parameter adds audio-lead/trail offsets at cut points (timeline supports A/V-linked clips with independent edges).
- **Per-section pacing**: styles can specify pacing curves (e.g. fast open, settle middle) enforced across sections rather than a single global target.
- **Montage vs continuity**: montage mode emits shot-list-driven rapid sequences from B-roll pools; continuity mode enforces longer takes and match-cut preference.
- **Music-synced cutting**: beat-grid detection (onset detection on the music track) as a snapping target + optional cut-on-beat style mode.

## Acceptance criteria (per feature)

Each feature ships with: timeline-schema support + server validation, render-path support, at least one integration test rendering a minimal timeline using it, and keyboard parity where applicable. Multi-asset additionally requires: project-level draft generation and per-asset cache correctness tests.

## Non-goals

Collaboration/multi-user editing, mobile, generative AI media (extend/generate), color grading beyond basics.
