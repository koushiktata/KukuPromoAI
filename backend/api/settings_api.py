"""LLM API keys: save / test / remove from the UI. Keys are write-only: the API never returns them,
only whether one is set plus its last 4 characters."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import KEY_PROVIDERS, env_key_name, write_env_value
from ..llm.configurable_provider import PRESETS, OpenAICompatibleProvider

router = APIRouter(prefix="/api/settings", tags=["settings"])
KEY_RE = re.compile(r"^[A-Za-z0-9_\-.:]{16,300}$")
SIGNUP = {"groq": "https://console.groq.com/keys", "gemini": "https://aistudio.google.com/apikey",
          "openrouter": "https://openrouter.ai/keys", "openai": "https://platform.openai.com/api-keys"}


class KeyIn(BaseModel):
    api_key: str = Field(min_length=16, max_length=300)


class TestIn(BaseModel):
    model: str | None = Field(default=None, max_length=100)


def _status(provider: str) -> dict:
    key = os.getenv(env_key_name(provider)) or os.getenv("LLM_API_KEY") or ""
    return {"provider": provider, "set": bool(key), "hint": f"••••{key[-4:]}" if len(key) >= 8 else "",
            "env_var": env_key_name(provider), "default_model": PRESETS[provider][1], "get_key_url": SIGNUP[provider]}


def _check(provider: str) -> None:
    if provider not in KEY_PROVIDERS:
        raise HTTPException(404, f"unknown provider; use one of {list(KEY_PROVIDERS)}")


@router.get("/keys")
def list_keys():
    return {"providers": [_status(p) for p in KEY_PROVIDERS] +
            [{"provider": "ollama", "set": True, "hint": "local, no key", "env_var": "",
              "default_model": PRESETS["ollama"][1], "get_key_url": "https://ollama.com"}]}


@router.put("/keys/{provider}")
def save_key(provider: str, body: KeyIn):
    _check(provider)
    key = body.api_key.strip()
    if not KEY_RE.match(key):
        raise HTTPException(422, "that doesn't look like an API key (no spaces or quotes; 16-300 characters)")
    write_env_value(env_key_name(provider), key)
    return _status(provider)


@router.delete("/keys/{provider}")
def remove_key(provider: str):
    _check(provider)
    write_env_value(env_key_name(provider), None)
    return _status(provider)


@router.post("/keys/{provider}/test")
def test_key(provider: str, body: TestIn | None = None):
    """One tiny request to the provider. Errors are returned without the key."""
    if provider != "ollama":
        _check(provider)
    key = os.getenv(env_key_name(provider)) or os.getenv("LLM_API_KEY") or ""
    try:
        llm = OpenAICompatibleProvider(provider, (body.model if body else None) or "", api_key=key, timeout=90, sleep=0)   # newer models can take ~45 s
        reply = llm._chat("Reply with JSON only.", 'Return {"ok": true}')
    except Exception as e:
        msg = str(e).replace(key, "••••") if key else str(e)
        return {"provider": provider, "ok": False, "model": PRESETS[provider][1], "error": msg[:300]}
    return {"provider": provider, "ok": True, "model": llm.model, "reply": reply[:80]}
