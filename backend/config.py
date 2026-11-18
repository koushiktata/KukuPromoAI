"""Central configuration. Everything is overridable with environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = Path(os.getenv("KUKU_ENV_FILE", ROOT / ".env"))
KEY_PROVIDERS = ("groq", "gemini", "openrouter", "openai")


def env_key_name(provider: str) -> str:
    return f"{provider.upper()}_API_KEY"


def write_env_value(name: str, value: str | None) -> None:
    """Set (or remove, when value is None) NAME=value in the .env file and in this process.
    The file is created with owner-only permissions; values are never logged."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == name:
            if value is not None and not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if value is not None and not done:
        out.append(f"{name}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(out) + "\n")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _load_dotenv() -> None:
    env = ENV_FILE
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:                       # empty template lines must not mask real environment variables
                os.environ.setdefault(k.strip(), v)


_load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.getenv("KUKU_DATA_DIR", ROOT / "data" / "scripts"))      # the default show
        self.shows_dir = Path(os.getenv("KUKU_SHOWS_DIR", ROOT / "data" / "shows"))     # uploaded shows
        self.output_dir = Path(os.getenv("KUKU_OUTPUT_DIR", ROOT / "outputs"))
        self.db_path = Path(os.getenv("KUKU_DB_PATH", ROOT / "outputs" / "kukupromo.db"))
        self.checkpoint_dir = Path(os.getenv("KUKU_CHECKPOINT_DIR", ROOT / "outputs" / "checkpoints"))
        self.prompts_dir = ROOT / "prompts"
        # LLM: "mock" = deterministic heuristic judge (no network). Otherwise any OpenAI-compatible provider.
        self.llm_provider = os.getenv("LLM_PROVIDER", "mock")
        self.llm_model = os.getenv("LLM_MODEL", "")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "")
        self.max_retries = int(os.getenv("MAX_RETRIES", "2"))
        self.llm_sleep = float(os.getenv("LLM_SLEEP_SECONDS", "2"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024)))
        # Scoring weights (our own assumption, NOT official Kuku criteria)
        self.weights = {
            "hook": float(os.getenv("W_HOOK", "0.25")),
            "cliffhanger": float(os.getenv("W_CLIFF", "0.30")),
            "standalone": float(os.getenv("W_STANDALONE", "0.20")),
            "emotion": float(os.getenv("W_EMOTION", "0.15")),
            "coherence": float(os.getenv("W_COHERENCE", "0.10")),
        }
        self.promo_min_s = 20.0
        self.promo_max_s = 60.0
        self.hook_window_s = 3.0

    def api_key(self) -> str:
        """Never logged or returned by the API."""
        return os.getenv("LLM_API_KEY") or os.getenv(f"{self.llm_provider.upper()}_API_KEY", "")


settings = Settings()
