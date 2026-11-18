"""API request/response schemas."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    version: str
    data_files: int
    provider: str
    api_key_set: bool
    keys_present: list[str] = Field(default_factory=list)   # provider names only, never the keys
    running_run: str | None = None


PROVIDER_PATTERN = "^(mock|groq|gemini|openrouter|openai|ollama)$"


class StartRequest(BaseModel):
    episodes: list[int] | None = Field(default=None, description="subset of episode numbers; default all")
    show: str | None = Field(default=None, max_length=64, description="show id from /api/shows; default 'default'")
    provider: str | None = Field(default=None, pattern=PROVIDER_PATTERN, description="single LLM (legacy)")
    providers: list[Annotated[str, Field(pattern=PROVIDER_PATTERN)]] | None = Field(
        default=None, max_length=5, description="one or more LLMs; several = judge panel")
    models: dict[str, str] | None = Field(default=None, description="model per provider, e.g. {'groq': '...'}")
    model: str | None = Field(default=None, max_length=100)
    max_retries: int = Field(default=2, ge=0, le=5)
    weights: dict[str, float] | None = None


class RunInfo(BaseModel):
    run_id: str
    status: str
    stage: str = ""
    progress: float = 0
    counts: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    errors: list = Field(default_factory=list)
    created_at: str = ""
    finished_at: str = ""
    config: dict = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    decision: Literal["not_reviewed", "approved", "rejected"]
    reason: str = Field(default="", max_length=500)
    reviewer: str = Field(default="", max_length=80)


class VerifyRequest(BaseModel):
    status: Literal["unreviewed", "verified", "incorrect", "needs_review"]
    note: str = Field(default="", max_length=500)
    reviewer: str = Field(default="", max_length=80)


class Summary(BaseModel):
    run: RunInfo | None
    show_name: str = ""
    show_id: str = ""
    judges: list[str] = Field(default_factory=list)
    episodes: int
    candidates: int
    passed_rules: int
    ranked: int
    new_viewer: int
    retarget: int
    processing_seconds: float | None
    review: dict
    secrets_total: int
    secrets_unverified: int
    flags_total: int
    flags_unreviewed: int
    high_severity_flags_unreviewed: int
    posting_warning: bool
