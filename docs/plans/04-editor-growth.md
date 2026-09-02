# Plan 4 — Editor Growth + Style v2

**Status: planned.** Depends on Plans 1–3. Feature-sized chunks, each independently shippable.

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
