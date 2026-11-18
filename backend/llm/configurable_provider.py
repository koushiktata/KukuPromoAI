"""Any OpenAI-compatible chat API (Groq, Gemini, OpenRouter, OpenAI, Ollama, vLLM...).
Swapping models = changing LLM_PROVIDER / LLM_MODEL / LLM_API_KEY. The key is never logged."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .base import JudgeRequest, JudgeResponse, JudgeVerdict, LLMProvider

PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("http://localhost:11434/v1", "llama3.1"),
}
PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "promo_analysis.txt"


def _prompt_parts() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    system, user = text.split("### USER", 1)
    return system.replace("### SYSTEM", "").strip(), user.strip()


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("model did not return JSON")
        return json.loads(m.group(0))


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, provider: str, model: str = "", base_url: str = "", api_key: str = "",
                 timeout: int = 120, sleep: float = 2.0):
        p_url, p_model = PRESETS.get(provider, ("", ""))
        self.base_url = (base_url or p_url).rstrip("/")
        self.model = model or p_model
        self._key = api_key
        self.timeout, self.sleep = timeout, sleep
        self.name = f"{provider}:{self.model}"
        if not self.base_url or not self.model:
            raise ValueError(f"unknown provider {provider!r}: set LLM_BASE_URL and LLM_MODEL")
        if not api_key and "localhost" not in self.base_url:
            raise ValueError(f"no API key for {provider}: set LLM_API_KEY or {provider.upper()}_API_KEY")

    def describe(self) -> dict:
        return {"provider": self.name, "base_url": self.base_url, "api_key_set": bool(self._key)}

    def _chat(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.2, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        # A real User-Agent is required: Cloudflare in front of Groq (and others) blocks Python's default one (error 1010).
        headers = {"Content-Type": "application/json", "User-Agent": "KukuPromoAI/1.0"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        for attempt in range(2):
            req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
                                         headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read())
                if self.sleep:
                    time.sleep(self.sleep)          # stay under free-tier rate limits
                return data["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:200]
                if e.code == 400 and "response_format" in msg and attempt == 0:
                    body.pop("response_format")
                    continue
                if e.code == 429:
                    wait = 20.0
                    m = re.search(r"try again in ([\d.]+)s", msg)
                    if m:
                        wait = float(m.group(1)) + 1
                    time.sleep(min(wait, 60))
                raise RuntimeError(f"HTTP {e.code} from {self.name}: {msg}")   # retry manager decides
        raise RuntimeError("unreachable")

    def judge(self, req: JudgeRequest) -> JudgeResponse:
        system, user_t = _prompt_parts()
        cands = "\n\n".join(
            f"### {c.candidate_id} ({c.kind}, {c.duration:.0f}s)\nHOOK: {c.hook_text}\nCLIFF: {c.cliff_text}\n{c.transcript}"
            for c in req.candidates)
        user = (user_t.replace("{story_so_far}", req.story_so_far or "(first episode)")
                .replace("{episode}", str(req.episode)).replace("{logline}", req.logline)
                .replace("{candidates}", cands))
        raw = self._chat(system, user)
        data = parse_json(raw)
        ids = {c.candidate_id for c in req.candidates}
        verdicts = []
        for v in data.get("verdicts", []):
            if v.get("candidate_id") not in ids:
                continue          # ignore anything the model invented
            sc = {k: float(v[k]) for k in ("hook", "cliffhanger", "standalone", "emotion", "coherence")
                  if isinstance(v.get(k), (int, float)) and 1 <= float(v[k]) <= 5}
            verdicts.append(JudgeVerdict(candidate_id=v["candidate_id"], scores=sc or None,
                                         why_it_works=str(v.get("why_it_works", ""))[:300],
                                         verdict=str(v.get("verdict", ""))[:40], comment=str(v.get("comment", ""))[:300]))
        return JudgeResponse(verdicts=verdicts, raw=raw, provider=self.name)


def make_provider(settings) -> LLMProvider:
    return make_providers(settings, [settings.llm_provider], {settings.llm_provider: settings.llm_model})


def make_providers(settings, names: list[str], models: dict[str, str] | None = None) -> LLMProvider:
    """One provider, or a judge panel when several are chosen. 'mock' is offline and can't join a panel."""
    import os
    from .ensemble import EnsembleProvider
    from .mock_provider import MockProvider
    names = [n for n in dict.fromkeys(names or ["mock"]) if n]          # de-duplicate, keep order
    if not names or names == ["mock"] or names == ["heuristic"] or names == [""]:
        return MockProvider()
    if "mock" in names:
        raise ValueError("mock (offline) can't be combined with real LLMs")
    models = models or {}
    built = []
    for n in names:
        key = os.getenv("LLM_API_KEY") or os.getenv(f"{n.upper()}_API_KEY", "")
        base = settings.llm_base_url if len(names) == 1 else ""
        built.append(OpenAICompatibleProvider(n, models.get(n) or (settings.llm_model if len(names) == 1 else ""),
                                              base, key, sleep=settings.llm_sleep))
    return built[0] if len(built) == 1 else EnsembleProvider(built)
