# Cutlass

AI video editor — upload a video, a multimodal model drafts the first cut for you.

## Pipeline

1. **Ingest** — upload an MP4/MOV; `ffprobe` extracts duration/fps/resolution.
2. **Sample** — frames extracted every ~2s (1s for short videos) at reduced resolution.
3. **Chunked analysis** — frames are batched and sent to a multimodal model, which labels each frame (`core`, `filler`, `dead_air`, `intro_outro`, `repetition`).
4. **Global pass** — a second model call sees all frame notes and picks contiguous keep-segments (the edit decision list, EDL) with context of the whole video.
5. **Preview** — the UI plays the original video, auto-skipping cut ranges; the timeline shows kept vs. cut.
6. **Render** — ffmpeg physically produces `final_cut.mp4` for download.

## Run (dev)

Requires Python 3.11+, ffmpeg on PATH, Node 20+.

```bash
# Backend
cd backend
pip install -r requirements.txt
GLM_API_KEY=sk-... uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

No API key? Develop without credits:

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

## Run (Docker)

```bash
docker build -t cutlass .
docker run -p 8000:8000 -v cutlass-data:/data -e GLM_API_KEY=sk-... cutlass
# open http://localhost:8000
```
