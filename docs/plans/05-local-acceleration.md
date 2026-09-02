# Plan 5 — Local Acceleration, Interop & Advanced AI

**Status: planned.** Long-horizon workstream; items are independent and get individually scheduled once Plans 1–4 are underway. This is where "own algorithms and kernels on accelerators" lives.

## Goal

Make the whole pipeline run flat-cost on local hardware (Windows/NVIDIA first, since that's the dev box), open interchange in *both* directions, and push the AI beyond prompt selection into learned preference.

## Local models & acceleration

- **faster-whisper service** — local Whisper-compatible endpoint (Word-level timestamps included) behind the existing provider seam; transcription stops depending on any cloud.
- **Local vision analysis** — Qwen2.5-VL class open VLM via Ollama/vLLM for frame/shot captioning; provider config selects local vs cloud per stage (vision local, selection cloud, etc.).
- **GPU decode & encode** — NVENC/DXVA2 for frame extraction, proxy generation, and render (hardware `-hwaccel` paths with CPU fallback); benchmark harness proves the speedup and guards regressions.
- **Own kernels** (CUDA → WGSL/WebGPU where sensible): audio peak computation, thumbnail/contact-sheet generation, (later) histogram/scene features. These are small, hot, and ours — the natural place to own acceleration without taking on a full filter framework.
- **Analysis quality upgrades**: DOVER-style aesthetic scoring and Moment-DETR-style highlight ranking as local models → per-shot scores feed the selection prompt as structured candidates instead of raw notes only.

## Interop (both directions)

- **OTIO import** — bring an edit *into* cutlass (Premiere/Resolve/FCP via OTIO adapters); the export side already exists from Plan 3.
- **Round-trip guarantees**: golden timelines survive export→import without semantic loss (CI test with sample timelines).
- **Headless/batch API + watch folders** — drop files in a folder → drafts appear; scriptable project creation; the automation niche nothing local serves today (validated by Mosaic/agent-tooling interest).

## Advanced AI

- **Style learning from exemplars** ("learn my style"): encode a user's past finished edits as measured statistics (retention, segment-length distribution, transition frequency, subject-mix) + captioned content; new drafts initialize from the learned profile (the IBM Watson *Morgan* exemplar pattern). User-visible as a "my style" preset that improves as you finish edits.
- **A/B variant drafts** — one asset set, N style variants generated in parallel; pick/merge branches.
- **Agentic refinement** — iterate on a draft via natural-language change requests ("tighten the intro", "more B-roll in the middle") implemented as targeted timeline mutations with undo, not full re-drafts.

## Acceptance criteria (per item, when scheduled)

- Every local-model path degrades gracefully to the cloud provider and is covered by the provider abstraction tests.
- Kernel implementations are benchmarked against the ffmpeg/CPU baseline in CI (performance smoke test, not just correctness).
- No new external service becomes a *required* dependency — full offline mode remains a supported configuration.

## Non-goals

Cloud sync/hosting, mobile clients, real-time collaboration, model training beyond lightweight preference statistics.
