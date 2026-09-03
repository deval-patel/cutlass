# Cutlass

AI video editor — upload a video, a multimodal model drafts the first cut for you.

Roadmap and architecture plans live in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Features

- **Upload** a single video (MP4/MOV/MKV/WebM/M4V/AVI) with extension, size, and content validation
- **Chunked frame analysis** — frames sampled every ~2s, batched to a multimodal model that labels each `core` / `filler` / `dead_air` / `intro_outro` / `repetition`
- **Audio transcription** (Whisper-compatible endpoint) with timestamps, fed into the edit decision
- **Global pass** — a second model call sees all frame notes + the transcript and picks keep-segments (the EDL) with whole-video context
- **Timeline preview** — the player auto-skips cut ranges; filmstrip thumbnails and an AI frame-label strip sit under the timeline
- **Editable EDL** — tweak segment boundaries, add/remove segments; the model's draft is just a starting point
- **Render** — ffmpeg physically produces `final_cut.mp4` for download; re-render after edits
- **Projects** — every upload is a project (assets → timeline with version history); deleting a project removes its rows and files
- **Durable jobs** — a worker queue with crash recovery (killed mid-analysis? work resumes on restart) and SSE progress updates
- **API** — `/api/v1` (projects, assets, timeline documents); the legacy `/api` endpoints keep working as a compatibility shim
- **Editor** — timeline page with drag-trim/slide/split/ripple-delete, snapping, undo/redo, keyboard map (space, JKL-style stepping, S, Del), waveform lane, and per-clip preview that plays the timeline
- **Exports** — FCPXML 1.9, CMX3600 EDL, and SRT (re-timed captions) from any timeline; rendered MP4 always matches the timeline duration

## Pipeline

1. **Ingest** — upload an MP4/MOV; `ffprobe` extracts duration/fps/resolution.
2. **Sample** — frames extracted every ~2s (1s for short videos) at reduced resolution.
3. **Chunked analysis** — frames are batched and sent to a multimodal model, which labels each frame (`core`, `filler`, `dead_air`, `intro_outro`, `repetition`).
4. **Global pass** — a second model call sees all frame notes and picks contiguous keep-segments (the edit decision list, EDL) with context of the whole video.
5. **Preview** — the UI plays the original video, auto-skipping cut ranges; the timeline shows kept vs. cut.
6. **Render** — ffmpeg physically produces `final_cut.mp4` for download.

## Run (dev)

Requires Python 3.11+, ffmpeg on PATH, Node 20+.

### Local configuration

Copy the template and drop in your key:

```bash
cp .env.example .env   # .env is gitignored — never committed
```

The backend loads `.env` from the repo root on startup; real environment
variables always take precedence over the file. All options are documented in
[.env.example](.env.example) — model endpoint, vision/text models,
transcription, sampling, and size limits. Without a key, `DRY_RUN=1` runs the
whole pipeline with stubbed model calls.

```bash
# Backend
cd backend
pip install -r requirements-dev.lock
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

No API key at all?

```bash
DRY_RUN=1 uvicorn app.main:app --reload
```

### Model config

Any OpenAI-compatible vision endpoint works:

| Env var | Default | Purpose |
|---|---|---|
| `GLM_API_KEY` | — | API key |
| `MODEL_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `VISION_MODEL` | `gpt-4o` | frame-labeling model |
| `TEXT_MODEL` | `gpt-4o-mini` | segment-selection model |
| `SAMPLE_INTERVAL_S` | `2.0` | frame sampling interval |
| `CHUNK_SIZE` | `40` | frames per model call |
| `TRANSCRIBE_ENABLED` | `1` | transcribe audio and feed it into edit decisions |
| `TRANSCRIBE_MODEL` | `whisper-1` | model for `/audio/transcriptions` |
| `TRANSCRIBE_CHUNK_S` | `600` | audio chunk length for transcription |
| `QUEUE_WORKERS` | `2` | concurrent analysis/render workers |
| `MAX_UPLOAD_GB` | `2.0` | upload size limit |

## Development workflow

Two stacks, both gated by the same checks in CI (`.github/workflows/ci.yml`):

| | Backend (`backend/`) | Frontend (`frontend/`) |
|---|---|---|
| Lint + format | `ruff` | `eslint` + `prettier` |
| Types | `mypy --strict` | `tsc --strict` |
| Tests | `pytest` (needs ffmpeg on PATH) | `vitest` + Testing Library |

```bash
# Backend — one-time setup
cd backend
pip install -r requirements-dev.lock

# The checks CI runs:
ruff check . && ruff format --check .
mypy app
python -m pytest

# Frontend — one-time setup
cd frontend
npm install

# The checks CI runs:
npm run lint
npm run typecheck
npm run test
npm run build
```

Optional local pre-commit hooks (same fixers, run on every `git commit`):

```bash
pip install pre-commit
pre-commit install
```

Dependency policy: `requirements*.txt` are the human-edited inputs;
`requirements*.lock` are the pinned, cross-platform installs used by CI and
Docker. Regenerate locks after editing inputs:

```bash
cd backend
uv pip compile requirements.txt -o requirements.lock --universal --python-version 3.12
uv pip compile requirements-dev.txt -o requirements-dev.lock --universal --python-version 3.12
```

### Presubmit (GitHub branch protection)

CI runs on every pull request and every push to `main`. To make PRs the only
way to land changes, enable branch protection once in GitHub:
**Repo → Settings → Branches → Add branch ruleset for `main`** → require the
`CI` workflow to pass before merging, and (optionally) require PRs with at
least one approval. CI cannot configure this for you.

## Tests

```bash
cd backend
python -m pytest
```

Requires ffmpeg/ffprobe on PATH (tests skip with a clear reason if missing).
The suite covers the EDL normalizer, GLM response parsing, upload validation,
transcription, job history, and the full upload → analyze → render → download
pipeline (in `DRY_RUN` mode, no API calls). `tests/test_production_serving.py`
additionally verifies the built frontend is served by FastAPI — the same path
the Docker container runs (it self-skips until `npm run build` has run once).

Frontend tests:

```bash
cd frontend
npm run test
```

## Run (Docker)

```bash
docker build -t cutlass .
docker run -p 8000:8000 -v cutlass-data:/data --env-file .env cutlass
# open http://localhost:8000
```

The image never bakes in `.env`; credentials enter only via `--env-file`/`-e`.
