import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# DRY_RUN=1 stubs the model with a heuristic EDL so the pipeline can be
# developed without spending API credits.
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

# Provider settings (OpenAI-compatible endpoint pattern; GLM by default).
MODEL_API_KEY = os.environ.get("GLM_API_KEY", "")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.openai.com/v1")
VISION_MODEL = os.environ.get("VISION_MODEL", "gpt-4o")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "gpt-4o-mini")

# Sampling
SAMPLE_INTERVAL_S = float(os.environ.get("SAMPLE_INTERVAL_S", "2.0"))
FRAME_WIDTH = int(os.environ.get("FRAME_WIDTH", "512"))
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "40"))

DATA_DIR = Path(os.environ.get("CUTLASS_DATA", BASE_DIR / "data"))
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "cutlass.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
