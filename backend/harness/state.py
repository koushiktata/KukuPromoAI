"""Structured run/task state (Pydantic). Serialised to JSON checkpoints after every task."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RunStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Task(BaseModel):
    task_id: str
    stage: str
    agent: str
    tool: str
    args: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_retries: int = 2
    critical: bool = True          # a failed critical task fails the run; others escalate to NEEDS_REVIEW
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    output: dict = Field(default_factory=dict)   # small summary only (counts, ids)


class RunState(BaseModel):
    run_id: str
    objective: str
    status: RunStatus = RunStatus.NOT_STARTED
    stage: str = ""
    config: dict = Field(default_factory=dict)
    tasks: list[Task] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    finished_at: str = ""
    metrics: dict = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    escalations: list[dict] = Field(default_factory=list)

    def task(self, task_id: str) -> Task:
        return next(t for t in self.tasks if t.task_id == task_id)

    @property
    def progress(self) -> float:
        done = sum(t.status in (TaskStatus.COMPLETED, TaskStatus.NEEDS_REVIEW, TaskStatus.FAILED) for t in self.tasks)
        return round(done / max(len(self.tasks), 1), 3)

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in TaskStatus}
        for t in self.tasks:
            out[t.status.value] += 1
        return out
