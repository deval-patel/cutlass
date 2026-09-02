# Plan 2 — Style-Controlled AI Drafts

**Status: planned.** First feature project after Plan 1. Research basis: [`editing-style-techniques.md`](../research/editing-style-techniques.md).

## Goal

The user controls *how* the AI edits: pick a preset (`shorts`, `cinematic`, `vlog`, `a-roll`, `b-roll`, `documentary`, `montage`, `travel-diary`, …), tune it with structured knobs, and/or describe the desired style in natural language — and the draft visibly reflects it. Changing style re-drafts cheaply (selection-only), enabling A/B comparison. Prompt changes become measured regressions, not vibes.

## Design

### EditStyle spec (backend/app/styles/)
```python
class EditStyle(BaseModel):
    preset_id: str                      # e.g. "cinematic"
    # Machine-checkable parameters (deterministically enforced post-selection):
    target_retention: float | None      # kept/original duration ratio target
    target_segment_len_s: float | None  # ASL proxy — target average segment length
    min_segment_s / max_segment_s: float | None
    max_segment_count: int | None       # cut-density cap (e.g. shorts: few, montage: many)
    cut_on: Literal["word", "sentence", "shot", "anywhere"]
    # Prose guidance (goes into the prompt verbatim):
    guidance: str                       # preset's editorial description
    user_brief: str = ""                # free-form natural language from the user
```
- Presets live in `backend/app/styles/presets/` as data (TOML/JSON) — adding one is a file, not code.
- `user_brief` is sandboxed: concatenated into the style section of the prompt only; it can never change output schemas or safety rules.

### Prompt harness (backend/app/prompts/)
- Prompts move out of inline f-strings into **versioned template files** with a changelog (`prompts/vN/select_segments.md`, `prompts/vN/label_frames.md`). Version recorded on every generated draft (stored with the timeline) — you can always tell which prompt produced what.
- A `PromptBuilder` composes: system role → **style contract** (rendered EditStyle: prose + explicit parameter table + hard rules like "respect min/max segment length") → context (frame notes, transcript with word timestamps) → strict output schema.
- **Structured output**: JSON schema attached to the request where the endpoint supports it; otherwise schema stated in-prompt + `jsonschema` validation on parse. One retry feeding the validation error back; then fail loudly (never silently degraded drafts).
- **Deterministic post-processing** (the part competitors don't have):
  1. normalize (sort/merge/clamp — reuse `edl.normalize_segments`),
  2. **pacing enforcement**: split over-long segments / merge over-short ones to move toward `target_segment_len_s` and `max_segment_count`, snapping splits to word/sentence/shot boundaries (never mid-word),
  3. retention guardrail: if kept ratio deviates from `target_retention` beyond tolerance, re-prompt once with the measured deviation ("you kept 82%, target ≤ 50%") before accepting.
- **Cut-point hygiene**: word-level timestamps (WhisperX-style alignment; v1 uses `verbose_json` segment boundaries + `timestamp_granularities[]` where supported) and PySceneDetect shot boundaries; selection prompt receives both so "cut at sentence boundaries" is enforceable, not aspirational.

### Re-draft loop
- Frame notes + transcript + shot list are cached per asset (already persisted — keep it that way).
- `POST /api/v1/projects/{id}/redraft` with a new EditStyle re-runs *only* selection + post-processing (one text-model call + deterministic passes): seconds, not minutes, so A/B-ing styles is practical.
- Drafts are stored as named timeline versions ("cinematic v1", "shorts v2") — compare/restore from the UI.

### Eval harness (backend/tests/golden/)
- Golden set: user's real footage + manually-approved cuts stored as fixtures (paths, not blobs, in git; large media gitignored).
- Metrics: selection IoU vs golden, retention ratio, pacing deviation (mean segment length vs target), cut-point violations (cuts mid-word/mid-shot count).
- Recorded model responses (JSON) replay in unit tests — prompt/template changes run against them in CI; live-model evals are a manual `make eval` target.
- Prompt changelog discipline: changing a template requires a golden-set note in the PR.

### UI
- Upload flow: style preset gallery (cards with name, description, pacing hint) + free-text brief field; editable after the fact.
- Draft panel: show the style that produced it + per-segment reasons (already exist) + measured stats (retention, avg segment length) so adherence is visible.

## Task breakdown

1. EditStyle model + preset files + presets endpoint; default preset = current behavior (baseline parity).
2. Prompt harness: template files, PromptBuilder, schema validation + retry, version stamping; dry-run provider extended to respect style params (so tests exercise pacing enforcement deterministically).
3. Pacing/retention enforcement passes with unit tests (property tests: output always satisfies hard constraints).
4. Wire `select_segments(..., style: EditStyle)` through analyzer; store style+prompt version with the draft.
5. Word timestamps + shot boundaries as selection inputs.
6. Re-draft endpoint + draft versioning; frontend style picker + brief + redraft button; stats display.
7. Eval harness + golden fixtures + CI replay.

## Acceptance criteria

- Same footage, two different presets → visibly different drafts (measured: different retention + segment-length distributions, not just reasons).
- Free-form brief changes the draft and is reflected per-preset; prompt injection via brief cannot alter the output schema or system rules (test).
- All hard style constraints (min/max length, count cap) hold on the *post-processed* output even when the model ignores them (property test).
- Re-draft with cached analysis completes without any vision-model call.
- Golden-set regression suite runs in CI with recorded responses.

## Non-goals

Timeline-aware style features (J/L cuts, per-section pacing — Plan 4), style learning from past edits (Plan 5), new vision models.
