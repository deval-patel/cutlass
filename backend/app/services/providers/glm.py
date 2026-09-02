import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, cast

import httpx

from ... import config
from ...models import FrameNote, FrameNoteLabel, Segment, TranscriptLine
from ...prompts.builder import PromptBuilder
from ...styles.models import EditStyle
from ...styles.presets import resolve_style
from .base import MultimodalProvider

logger = logging.getLogger(__name__)

VALID_LABELS = {"core", "filler", "dead_air", "intro_outro", "repetition", "other"}

# Module-level builder: tests construct providers without __init__, so the
# templates must not depend on instance state.
_builder = PromptBuilder()


class GLMProvider(MultimodalProvider):
    def __init__(self) -> None:
        if not config.MODEL_API_KEY:
            raise RuntimeError("MODEL_API_KEY not set (set GLM_API_KEY or run with DRY_RUN=1)")
        self._headers = {"Authorization": f"Bearer {config.MODEL_API_KEY}"}

    def _chat(self, model: str, messages: list[dict[str, Any]]) -> str:
        resp = httpx.post(
            f"{config.MODEL_BASE_URL}/chat/completions",
            headers=self._headers,
            json={"model": model, "messages": messages, "temperature": 0.2},
            timeout=300,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise RuntimeError(f"non-text model response ({type(content).__name__})")
        return content

    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        content: list[dict[str, Any]] = [{"type": "text", "text": _builder.label_frames()}]
        for ts, path in frames:
            b64 = base64.b64encode(path.read_bytes()).decode()
            content.append({"type": "text", "text": f"t={ts:.1f}s"})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        raw = self._chat(config.VISION_MODEL, [{"role": "user", "content": content}])
        return [self._parse_note(item) for item in _extract_json(raw) if isinstance(item, dict)]

    def _parse_note(self, item: dict[str, Any]) -> FrameNote:
        label = str(item.get("label", "other"))
        checked = label if label in VALID_LABELS else "other"
        return FrameNote(
            timestamp_s=float(item.get("t", 0)),
            description=str(item.get("description", "")),
            label=cast(FrameNoteLabel, checked),
        )

    def transcribe(self, audio: Path, duration_s: float) -> list[TranscriptLine]:
        with audio.open("rb") as f:
            resp = httpx.post(
                f"{config.MODEL_BASE_URL}/audio/transcriptions",
                headers=self._headers,
                files={"file": (audio.name, f, "audio/wav")},
                data={
                    "model": config.TRANSCRIBE_MODEL,
                    "response_format": "verbose_json",
                },
                timeout=600,
            )
        resp.raise_for_status()
        data = resp.json()
        segments = data.get("segments") or []
        if segments:
            return [
                TranscriptLine(
                    start_s=float(s.get("start", 0)),
                    end_s=float(s.get("end", 0)),
                    text=str(s.get("text", "")).strip(),
                )
                for s in segments
                if str(s.get("text", "")).strip()
            ]
        # Endpoints that only return plain text: one line covering the chunk.
        text = str(data.get("text", "")).strip()
        return [TranscriptLine(start_s=0, end_s=duration_s, text=text)] if text else []

    def select_segments(
        self,
        notes: list[FrameNote],
        total_duration_s: float,
        transcript: list[TranscriptLine] | None = None,
        style: EditStyle | None = None,
        feedback: str | None = None,
    ) -> list[Segment]:
        """One global pass over the notes (+ transcript), with a single
        validation-retry and an optional retention-feedback re-prompt."""
        resolved = style if style is not None else resolve_style(None, None)
        prompt = self._selection_prompt(notes, total_duration_s, transcript, resolved)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        error: str | None = None
        for attempt in range(2):
            raw = self._chat(config.TEXT_MODEL, messages)
            try:
                segments = _coerce_segments(_extract_json(raw), total_duration_s)
            except ValueError as exc:
                error = str(exc)
                logger.warning("invalid selection response (attempt %d): %s", attempt + 1, error)
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": raw},
                    _builder.select_segments_repair(raw, error),
                ]
                continue
            if segments:
                return segments
            error = "response contained no usable keep-segments"
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": raw},
                _builder.select_segments_repair(raw, error),
            ]
        raise ValueError(f"model selection failed after retry: {error}")

    def _selection_prompt(
        self,
        notes: list[FrameNote],
        total_duration_s: float,
        transcript: list[TranscriptLine] | None,
        style: EditStyle,
    ) -> str:
        notes_text = "\n".join(
            f"- {n.timestamp_s:.1f}s [{n.label}]: {n.description}" for n in notes
        )
        if transcript:
            transcript_intro = ", plus the video's audio transcript with timestamps"
            transcript_block = (
                "\nTranscript:\n"
                + "\n".join(
                    f"[{line.start_s:.1f}-{line.end_s:.1f}s] {line.text}" for line in transcript
                )
                + "\n"
            )
        else:
            transcript_intro = ""
            transcript_block = ""
        return _builder.select_segments(
            duration_s=total_duration_s,
            style=style,
            transcript_intro=transcript_intro,
            transcript_block=transcript_block,
            notes=notes_text,
        )


def _coerce_segments(items: list[Any], total_duration_s: float) -> list[Segment]:
    """Validate + clamp model output. Raises ValueError when nothing usable."""
    segments: list[Segment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, float(item.get("start_s", 0)))
            end = min(total_duration_s, float(item.get("end_s", 0)))
        except (TypeError, ValueError):
            continue
        if end > start:
            segments.append(
                Segment(
                    start_s=start,
                    end_s=end,
                    reason=str(item.get("reason", "")),
                    confidence=float(item.get("confidence", 1.0)),
                )
            )
    if not segments:
        raise ValueError("no valid keep-segments could be parsed")
    return segments


def _extract_json(raw: str) -> list[Any]:
    """Pull the first JSON array out of a model response (handles code fences)."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON array in model response: {raw[:200]}")
    parsed: list[Any] = json.loads(match.group(0))
    return parsed
