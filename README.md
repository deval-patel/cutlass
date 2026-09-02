# Cutlass

AI video editor — upload a video, a multimodal model drafts the first cut for you.

## Features

- **Upload** a single video (MP4/MOV/MKV/WebM/M4V/AVI) with extension, size, and content validation
- **Chunked frame analysis** — frames sampled every ~2s, batched to a multimodal model that labels each `core` / `filler` / `dead_air` / `intro_outro` / `repetition`
- **Audio transcription** (Whisper-compatible endpoint) with timestamps, fed into the edit decision
- **Global pass** — a second model call sees all frame notes + the transcript and picks keep-segments (the EDL) with whole-video context
- **Timeline preview** — the player auto-skips cut ranges; filmstrip thumbnails and an AI frame-label strip sit under the timeline
- **Editable EDL** — tweak segment boundaries, add/remove segments; the model's draft is just a starting point
- **Render** — ffmpeg physically produces `final_cut.mp4` for download; re-render after edits
- **Job history** — every upload is listed on the home page and can be reopened

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
pip install -r requirements.txt
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
| `MAX_UPLOAD_GB` | `2.0` | upload size limit |

## Tests

```bash
cd backend
python -m pytest tests -q
```

Requires ffmpeg/ffprobe on PATH. The suite covers the EDL normalizer, GLM
response parsing, upload validation, transcription, job history, and the full
upload → analyze → render → download pipeline (in `DRY_RUN` mode, no API
calls). `tests/test_production_serving.py` additionally verifies the built
frontend is served by FastAPI — the same path the Docker container runs.

## Run (Docker)

```bash
docker build -t cutlass .
docker run -p 8000:8000 -v cutlass-data:/data --env-file .env cutlass
# open http://localhost:8000
```

The image never bakes in `.env`; credentials enter only via `--env-file`/`-e`.
