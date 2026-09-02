# Cutlass Roadmap

**Vision.** Cutlass is a self-hosted AI video editor for people who come home from a trip with hours of footage and zero will to edit it. Upload raw clips → transcription + multimodal analysis → an LLM drafts the rough cut **in a style you control** → refine in a built-in lightweight timeline editor → render and export. Everything runs on your machine and your choice of model (cloud API today, local models tomorrow); your footage never has to leave it.

**Why this can be a product, not just a script.** Every serious AI rough-cut tool on the market (Eddie AI, Kino, Threadline, Mosaic, Opus Clip, Gling) is closed-source cloud SaaS metered by credits, and every local/open tool stops at silence removal. No product combines self-hosted privacy, multimodal selection that works on *non-talking-head* footage, a built-in editor that closes the loop, and prompt-controllable editorial style. Full research: [`docs/research/product-landscape.md`](research/product-landscape.md) and [`docs/research/editing-style-techniques.md`](research/editing-style-techniques.md).

## Where the codebase stands today (Sept 2026)

- FastAPI + React 18/Vite + SQLite + ffmpeg subprocess; OpenAI-compatible provider (GLM by default), `DRY_RUN` stub for keyless dev/tests.
- Pipeline: probe → sample 1 frame/2s → optional chunked Whisper transcription → chunked vision labeling (`core|filler|dead_air|intro_outro|repetition`) → one global text-model pass that returns a flat segment list (`{start_s, end_s, reason, confidence}`).
- Preview is client-side auto-skip over the source video; editing is numeric start/end fields; export is a single ffmpeg select-filter render.
- **No style/preset/user-brief input exists anywhere** — all editorial judgment is baked into two hard-coded prompts (`backend/app/services/providers/glm.py`).
- Backend has an integration test suite; there is no CI, no linting, no type checking, no frontend tests, no dependency lock.

## Plan index (build order)

| # | Plan | Status | What it delivers |
|---|------|--------|------------------|
| 0 | [Engineering foundation](plans/00-foundation.md) | ✅ implemented | Lint/type/test/format on both stacks, CI on every PR, pre-commit, Docker hardening, TypeScript |
| 1 | [Core architecture for scale](plans/01-core-architecture.md) | planned | Project→Asset→Timeline model, layered backend, real migrations, job queue, SSE progress, API v1 |
| 2 | [Style-controlled AI drafts](plans/02-style-controlled-drafts.md) | planned | EditStyle presets + natural-language briefs, prompt harness with validation + pacing enforcement, re-draft loop, eval harness |
| 3 | [Editor MVP](plans/03-editor-mvp.md) | planned | Real timeline UI (drag-trim, playhead, zoom, snap, shortcuts, undo), waveform, timeline rendering, MP4 + FCPXML/EDL export |
| 4 | [Editor growth + style v2](plans/04-editor-growth.md) | planned | Transitions, titles, speed ramps, music + ducking, caption burn-in, proxy workflow; style gains timeline-aware knobs (J/L cuts, per-section pacing) |
| 5 | [Local acceleration + interop + advanced AI](plans/05-local-acceleration.md) | planned | faster-whisper/local VLM, GPU decode, own kernels, OTIO import, aesthetic/highlight scoring, style learning, batch/watch-folder |

Sequencing rationale: Plan 1 is the shared prerequisite (the editor and style-v2 both need the timeline document model; multi-clip projects need Project/Asset). Plan 2 ships before the editor because it attacks the core pain — a *good* draft from a pile of footage — and works on the current flat-segment model. Decisions are recorded as [ADRs](adr/).

## Product principles

1. **Local-first, model-agnostic.** Self-hosted by default; any OpenAI-compatible endpoint or local model. No telemetry, no footage uploads we don't control.
2. **The draft is a starting point, not a verdict.** Every AI decision is inspectable (reasons, labels, scores) and cheap to regenerate (re-run selection over cached analysis with a new style).
3. **Own the hot paths.** Analysis, waveform, thumbnails, rendering get our own accelerated implementations when it matters (Plan 5) — flat cost instead of per-hour credits.
4. **No slop.** PR-gated CI (lint + types + tests) on every change; architecture docs and ADRs for anything load-bearing; production-quality code from commit one.
5. **Single-user now, multi-user-ready.** No auth yet, but seams (`user_id`, stateless API, repository layer) so accounts can be added without a rewrite.
