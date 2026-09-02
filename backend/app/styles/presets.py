"""Preset library: adding a style is a JSON file in presets/, not code."""

import json
import logging
from pathlib import Path
from typing import Any

from .models import DEFAULT_PRESET_ID, EditStyle, PresetSummary

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent / "presets"


def _load_file(path: Path) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def _to_edit_style(doc: dict[str, Any], fallback_id: str) -> EditStyle:
    style = dict(doc.get("style") or {})
    style.setdefault("preset_id", doc.get("preset_id", fallback_id))
    return EditStyle.model_validate(style)


def list_presets() -> list[PresetSummary]:
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        doc = _load_file(path)
        presets.append(
            PresetSummary(
                preset_id=doc.get("preset_id", path.stem),
                name=doc.get("name", path.stem),
                description=doc.get("description", ""),
                pacing=doc.get("pacing", ""),
            )
        )
    return presets


def load_preset(preset_id: str) -> EditStyle:
    """Load a preset by id; unknown ids raise KeyError (API maps to 400/422)."""
    path = PRESETS_DIR / f"{preset_id}.json"
    if not path.exists():
        raise KeyError(preset_id)
    return _to_edit_style(_load_file(path), path.stem)


def resolve_style(preset_id: str | None, user_brief: str | None) -> EditStyle:
    """Preset + the user's free-form brief. Unknown preset falls back to the
    default (with the invalid id noted in guidance) rather than failing the
    draft — a style hiccup shouldn't kill an otherwise-good analysis."""
    pid = preset_id or DEFAULT_PRESET_ID
    try:
        style = load_preset(pid)
    except KeyError:
        logger.warning("unknown style preset %r; using default", pid)
        style = load_preset(DEFAULT_PRESET_ID)
    style.user_brief = (user_brief or "").strip()
    return style
