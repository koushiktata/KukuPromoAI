"""FastAPI app. Run:  uvicorn backend.main:app --reload --port 8000"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import agents, episodes, processing, promos, reports, reviews, settings_api, shows
from .api.deps import get_orchestrator
from .api.schemas import Health
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
VERSION = "1.0.0"

app = FastAPI(title="KukuPromo AI", version=VERSION,
              description="Agentic microdrama promo discovery: find, validate, rank and review 20-60s promos.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
                   allow_methods=["*"], allow_headers=["*"])

for r in (episodes.router, processing.router, promos.router, reviews.router, agents.router, reports.router,
          settings_api.router, shows.router):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    get_orchestrator()      # builds the orchestrator now, which unlocks runs interrupted by a restart


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.getLogger("kukupromo.api").exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error - see server log"})


@app.get("/api/health", response_model=Health)
def health():
    import os
    orch = get_orchestrator()
    generic = bool(os.getenv("LLM_API_KEY"))
    present = [p for p in ("groq", "gemini", "openrouter", "openai")
               if generic or os.getenv(f"{p.upper()}_API_KEY")] + ["ollama"]
    return Health(status="ok", version=VERSION, data_files=len(list(settings.data_dir.glob("*.txt"))),
                  provider=settings.llm_provider if settings.llm_provider != "mock" else "mock (offline heuristic)",
                  api_key_set=bool(settings.api_key()), keys_present=present, running_run=orch.running())
