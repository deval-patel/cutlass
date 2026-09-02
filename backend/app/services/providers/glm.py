import base64
import json
import re
from pathlib import Path

import httpx

from ... import config
from ...models import FrameNote, Segment
from .base import MultimodalProvider

VALID_LABELS = {"core", "filler", "dead_air", "intro_outro", "repetition", "other"}

FRAME_PROMPT = """\
You are a video editor's assistant. You will receive frames sampled from one \
video, in chronological order. Each image is preceded by its timestamp.

For EVERY frame, output a JSON array (and nothing else) where each element is:
{{"t": <timestamp seconds>, "description": "<what is shown / happening>", "label": "<one of core|filler|dead_air|intro_outro|repetition>"}}

- core: meaningful content the video exists to deliver
- filler: tangential rambling, ums/hesitation shots, low-value asides
- dead_air: nothing happening (black frames, idle screen, silence pauses)
- intro_outro: title cards, intros, outros, branding, end screens
- repetition: visually repeating what an earlier frame already covered\
"""

GLOBAL_PROMPT = """\
You are editing a video of total duration {duration:.0f}s. Below are per-frame \
notes from the whole video (timestamp, description, label). Produce the FIRST \
DRAFT CUT: select contiguous keep-segments containing the meaningful content \
while cutting dead air, filler, intros/outros, and repetition.

Output ONLY a JSON array of keep-segments:
[{{"start_s": <float>, "end_s": <float>, "reason": "<why kept>", "confidence": <0-1>}}]

Rules: segments must be chronological and non-overlapping, cover at most the \
video duration, and keep the video coherent (no cuts mid-sentence at boundaries \
when avoidable — pad boundaries slightly).

Notes:
{notes}\
"""


class GLMProvider(MultimodalProvider):
    def __init__(self) -> None:
        if not config.MODEL_API_KEY:
            raise RuntimeError(
                "MODEL_API_KEY not set (set GLM_API_KEY or run with DRY_RUN=1)"
            )
        self._headers = {"Authorization": f"Bearer {config.MODEL_API_KEY}"}

    def _chat(self, model: str, messages: list[dict]) -> str:
        resp = httpx.post(
            f"{config.MODEL_BASE_URL}/chat/completions",
            headers=self._headers,
            json={"model": model, "messages": messages, "temperature": 0.2},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        content: list[dict] = [{"type": "text", "text": FRAME_PROMPT}]
        for ts, path in frames:
            b64 = base64.b64encode(path.read_bytes()).decode()
            content.append({"type": "text", "text": f"t={ts:.1f}s"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        raw = self._chat(config.VISION_MODEL, [{"role": "user", "content": content}])
        return [self._parse_note(item) for item in _extract_json(raw) if isinstance(item, dict)]

    def _parse_note(self, item: dict) -> FrameNote:
        label = str(item.get("label", "other"))
        return FrameNote(
            timestamp_s=float(item.get("t", 0)),
            description=str(item.get("description", "")),
            label=label if label in VALID_LABELS else "other",
        )

    def select_segments(self, notes: list[FrameNote], total_duration_s: float) -> list[Segment]:
        notes_text = "\n".join(
            f"- {n.timestamp_s:.1f}s [{n.label}]: {n.description}" for n in notes
        )
        prompt = GLOBAL_PROMPT.format(duration=total_duration_s, notes=notes_text)
        raw = self._chat(config.TEXT_MODEL, [{"role": "user", "content": prompt}])
        items = _extract_json(raw)
        segments = []
        for item in items:
            if not isinstance(item, dict):
                continue
            start = max(0.0, float(item.get("start_s", 0)))
            end = min(total_duration_s, float(item.get("end_s", 0)))
            if end > start:
                segments.append(Segment(
                    start_s=start,
                    end_s=end,
                    reason=str(item.get("reason", "")),
                    confidence=float(item.get("confidence", 1.0)),
                ))
        return segments


def _extract_json(raw: str) -> list:
    """Pull the first JSON array out of a model response (handles code fences)."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON array in model response: {raw[:200]}")
    return json.loads(match.group(0))
