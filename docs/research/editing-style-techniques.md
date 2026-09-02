# Editing-Style Control: Technical & Research Background

How the edit decision works today in Cutlass, what research exists for controlling it, and the techniques Plan 2 borrows. Companion doc: [`product-landscape.md`](product-landscape.md).

## How Cutlass decides the edit today

Two hard-coded prompts carry all editorial judgment (`backend/app/services/providers/glm.py`):

1. **Frame labeling (vision pass)** — sampled frames (1 per 2s, 512px) are batched 40/call; the model returns `{t, description, label}` per frame with a 5-label taxonomy: `core | filler | dead_air | intro_outro | repetition`.
2. **Segment selection (text pass)** — one call sees all frame notes (+ transcript lines) and returns keep-segments `{start_s, end_s, reason, confidence}` with rules like "never cut mid-sentence when transcript boundaries are clear."

There is **no style/preset/brief input anywhere** — the upload endpoint takes only the file. The "style" is whatever the default prompts imply. The provider ABC (`providers/base.py`) is the clean seam for adding an `EditStyle` parameter.

This architecture is, incidentally, the LAVE pattern already half-built — which the research says is the right one.

## Relevant research

### LLM-driven editing planning
- **LAVE** (Google, CHI 2024, [arXiv:2402.10294](https://arxiv.org/abs/2402.10294)) — LLM agent plans clip sequencing over *video captions*, with language-augmented editing. Key takeaway: have the LLM work over textual descriptions of shots (cheap, controllable, inspectable) rather than raw pixels; vision models produce the descriptions once, and many editing iterations run over the text. This is exactly our notes → selection split; Plan 2 doubles down on it (style only affects the selection pass, so re-styling is cheap).
- **IBM Watson "Morgan" trailer** (2016, [paper](https://www.researchgate.net/publication/320543371_Harnessing_AI_for_Augmenting_Creativity_Application_to_Movie_Trailer_Creation)) — first AI movie trailer: Watson tagged scenes (24 emotions, ~22k categories), learned patterns from reference trailers, scored candidate scenes; human assembled. Takeaway: **exemplar learning** — "edit like this reference" — is the proven mechanism for a future "learn my style from my past edits" feature.
- **Director-agent systems** — FilmAgent ([arXiv:2501.12909](https://arxiv.org/abs/2501.12909)), AutoDirector ([arXiv:2408.11564](https://arxiv.org/abs/2408.11564)), VideoDirectorGPT, VideoDiff. Multi-agent "director/editor" roleplay; useful mainly as validation that structured editing contracts + role prompts work.

### Style as measurable statistics (the core insight for our style presets)
- **James Cutting's film statistics** ([Attention and the Evolution of Hollywood Film](https://journals.sagepub.com/doi/abs/10.1177/0956797610361679), [Quicker, faster, darker](https://pmc.ncbi.nlm.nih.gov/articles/PMC3485803/)) — shot-length distributions in Hollywood film follow measurable 1/f patterns and average shot length (ASL) has declined steadily for decades. **Implication:** "pacing" is not vibes — a style preset can specify a target ASL / cut-density curve and the pipeline can *verify and enforce* it deterministically. No competitor does this; their "styles" are caption/font cosmetics.
- **Standard editing taxonomy** — continuity vs montage vs graphic/rhythmic/tonal matching; J-cut (audio leads picture) and L-cut (audio trails) as first-class timeline parameters; cut-on-action windows ([ITU taxonomy](https://www.ituonline.com/blogs/editing-film-definition/), [Adobe on J/L cuts](https://www.adobe.com/creativecloud/video/post-production/cuts-in-film/l-and-j-cut.html)). This is the vocabulary presets should expose, not just "vibe words."

### Selection-quality signals (candidate ranking before/alongside the LLM)
- **Moment-DETR / QVHighlights** ([arXiv:2107.09609](https://arxiv.org/abs/2107.09609), [repo](https://github.com/jayleicn/moment_detr)) — joint moment retrieval + highlight detection with saliency scores; follow-ups QD-DETR, SG-DETR, VERIFIED. Trainable rankers for "what's the good part."
- **DOVER** ([arXiv:2211.04894](https://arxiv.org/abs/2211.04894)) — disentangles aesthetic from technical quality for no-reference video QA; ideal for ranking travel B-roll candidates.
- **Ego4D + NLQ** ([ego4d-data.org](https://ego4d-data.org/)) — egocentric moment retrieval; relevant to action-cam footage. **Prosody** — Threadline's intonation-driven assembly validates using audio signal (energy, pitch, speech rate) beyond transcript text.

### Infrastructure techniques worth borrowing
- **WhisperX** ([GitHub](https://github.com/m-bain/whisperx)) — forced-alignment **word-level timestamps** (+ diarization), ~70x realtime with faster-whisper. Word boundaries are what make cuts land cleanly.
- **Shot boundary detection** — PySceneDetect (CPU-friendly), TransNetV2 (accurate on graduals) ([scenedetect.com/similar](https://www.scenedetect.com/similar/)). Cut points snapped to shot boundaries avoid visual jank.
- **Qwen2.5-VL** ([blog](https://qwenlm.github.io/blog/qwen2.5-vl/)) — open-weights VLM with 1h+ video comprehension and second-level localization; the practical local vision model for Plan 5.
- **Reference open pipelines** — mazsola2k/ai-video-editor ([GitHub](https://github.com/mazsola2k/ai-video-editor)): 2s frame sampling → local VLM boring/interesting scoring → CLIP features → FCPXML timeline. Proves the local-first stack works end to end.
- **Interchange formats** — Eddie's export matrix (Premiere/FCP/Resolve/Avid EDL/**OTIO**) is the de facto checklist; OTIO is the right internal anchor because it converts to all of them.

## Design conclusions feeding Plan 2

1. **Style = structured contract + prose.** Presets carry machine-checkable parameters (target retention ratio, target ASL/cut density, min/max segment length, montage-vs-continuity, J/L allowances) *and* natural-language guidance; the user's free-form brief layers on top. The LLM gets both; the deterministic post-processor enforces the measurable ones.
2. **Iterate cheaply over cached analysis.** Frame notes + transcript are stored; re-drafting with a new style re-runs only the selection pass (one text-model call) — enables A/B style comparison.
3. **Ground truth via golden sets.** Prompt changes are regressions, not vibes: keep recorded model responses, golden cuts from real footage, and metrics (selection IoU, pacing deviation, retention) in CI.
4. **Cut-point hygiene first.** Word-level timestamps + shot boundaries improve *every* style before any prompt cleverness.
