"""LLM provider interface. Providers only SCORE and DESCRIBE candidates that code generated;
they never create timestamps, so they cannot certify their own cut points."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class JudgeCandidate(BaseModel):
    candidate_id: str
    kind: str
    duration: float
    transcript: str                 # timestamped lines inside the segments
    hook_text: str
    cliff_text: str
    labels: list[str] = Field(default_factory=list)
    heuristic: dict[str, float] = Field(default_factory=dict)


class JudgeRequest(BaseModel):
    episode: int
    story_so_far: str
    logline: str
    candidates: list[JudgeCandidate]


class JudgeVerdict(BaseModel):
    candidate_id: str
    scores: dict[str, float] | None = None     # hook/cliffhanger/standalone/emotion/coherence, 1-5
    why_it_works: str = ""
    verdict: str = ""                          # Postable | Needs edit | Skip
    comment: str = ""
    panel: list[dict] = Field(default_factory=list)   # per-model scores when several LLMs judge
    agreement: str = ""                               # high | medium | low (multi-LLM only)


class JudgeResponse(BaseModel):
    verdicts: list[JudgeVerdict]
    raw: str = ""
    provider: str = ""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def judge(self, req: JudgeRequest) -> JudgeResponse: ...

    def describe(self) -> dict:
        return {"provider": self.name}
