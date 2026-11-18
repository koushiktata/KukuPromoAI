"""Shared domain models (Pydantic) used by pipeline, agents, API and exports."""
from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SourceRef(BaseModel):
    file: str
    line_start: int
    line_end: int
    event_ids: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    order: int
    episode: int
    start: float
    end: float
    start_ts: str
    end_ts: str
    duration: float
    source: SourceRef | None = None
    reason: str = ""


class Moment(BaseModel):
    """A quoted moment (hook or cliffhanger) with its exact source."""
    text: str
    episode: int
    time: float
    ts: str
    event_id: str
    kind: str = ""
    labels: dict[str, float] = Field(default_factory=dict)


class Scores(BaseModel):
    """All criteria on a 1-5 scale."""
    hook: float = 0
    cliffhanger: float = 0
    standalone: float = 0
    emotion: float = 0
    coherence: float = 0
    overall: float = 0
    source: str = "heuristic"        # heuristic | llm:<model> | blended
    explanation: str = ""


class Check(BaseModel):
    name: str
    passed: bool
    severity: str = "hard"           # hard -> INVALID when failed, soft -> NEEDS_REVIEW
    detail: str = ""


class Validation(BaseModel):
    status: ValidationStatus = ValidationStatus.NEEDS_REVIEW
    checks: list[Check] = Field(default_factory=list)


class Category(BaseModel):
    new_viewer: bool = False
    retarget: bool = False
    spoiler_secret_ids: list[str] = Field(default_factory=list)
    explanation: str = ""


class Judge(BaseModel):
    verdict: str = ""                # Postable | Needs edit | Skip
    comment: str = ""
    provider: str = ""
    panel: list[dict] = Field(default_factory=list)   # one entry per LLM when a judge panel is used
    agreement: str = ""                               # high | medium | low


class AltCut(BaseModel):
    promo_id: str
    segments: list[Segment]
    duration: float
    overall: float
    valid: bool
    difference: str


class Promo(BaseModel):
    promo_id: str
    kind: str                        # continuous | multi_segment | cross_episode
    segments: list[Segment]
    duration: float
    hook: Moment | None = None
    cliffhanger: Moment | None = None
    why_it_works: str = ""
    labels: dict[str, float] = Field(default_factory=dict)
    rule_hook: float = 0             # raw rule strengths (unbounded)
    rule_cliff: float = 0
    rule_score: float = 0
    scores: Scores = Field(default_factory=Scores)
    judge: Judge = Field(default_factory=Judge)
    validation: Validation = Field(default_factory=Validation)
    category: Category = Field(default_factory=Category)
    content_flag_ids: list[str] = Field(default_factory=list)
    group_id: str = ""
    alternatives: list[AltCut] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    rank: int | None = None
    posting_priority: str = ""
    rank_reason: str = ""

    @property
    def episodes(self) -> list[int]:
        return sorted({s.episode for s in self.segments})


def promo_id_for(segments: list[Segment]) -> str:
    """Stable id from the cut itself, so editor reviews survive re-runs."""
    key = "|".join(f"{s.episode}:{s.start:.2f}-{s.end:.2f}" for s in segments)
    return "P" + hashlib.sha1(key.encode()).hexdigest()[:10]


class Secret(BaseModel):
    secret_id: str
    theme: str
    description: str
    reveal_episode: int
    evidence: list[dict] = Field(default_factory=list)   # {episode, ts, snippet}
    severity: str = "medium"         # low | medium | high
    confidence: float = 0.5
    patterns: list[str] = Field(default_factory=list)
    source: str = "heuristic"
    ai_generated: bool = True


class ContentFlag(BaseModel):
    flag_id: str
    flag_type: str
    episode: int
    start: float
    end: float
    ts: str
    snippet: str
    severity: str
    confidence: float
    event_ids: list[str] = Field(default_factory=list)
