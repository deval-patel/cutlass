import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_apply_dotenv_loads_values(tmp_path, monkeypatch):
    from app import config

    env = tmp_path / ".env"
    env.write_text("# comment\nFOO=bar\nGLM_API_KEY=test-key-123\n")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)

    config._apply_dotenv(env)

    assert os.environ["FOO"] == "bar"
    assert os.environ["GLM_API_KEY"] == "test-key-123"

    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)


def test_apply_dotenv_missing_file_is_noop(tmp_path):
    from app import config

    config._apply_dotenv(tmp_path / "does-not-exist.env")  # must not raise


def test_real_env_wins_over_dotenv(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setenv("GLM_API_KEY", "from-real-env")
    env = tmp_path / ".env"
    env.write_text("GLM_API_KEY=from-file\n")

    config._apply_dotenv(env)

    assert os.environ["GLM_API_KEY"] == "from-real-env"


def test_env_example_is_committed_template():
    example = REPO_ROOT / ".env.example"
    assert example.exists(), ".env.example must exist as the committed template"
    values = dotenv_values(example)
    keys = set(values)
    for required in (
        "GLM_API_KEY",
        "MODEL_BASE_URL",
        "VISION_MODEL",
        "TEXT_MODEL",
        "TRANSCRIBE_ENABLED",
        "DRY_RUN",
    ):
        assert required in keys, f"{required} missing from .env.example"


def test_local_env_is_gitignored():
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "-v", ".env"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, ".env is NOT covered by .gitignore"
    assert ".gitignore" in result.stdout
