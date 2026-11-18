"""Runs the plan: dependency checks, bounded retries, escalation, checkpoint after every task."""
from __future__ import annotations

import time
from typing import Any, Callable

from .checkpoint import CheckpointStore
from .retry_manager import RetryManager
from .state import RunState, RunStatus, Task, TaskStatus, now
from .tracing import Tracer

DONE = (TaskStatus.COMPLETED, TaskStatus.NEEDS_REVIEW)


class Executor:
    def __init__(self, state: RunState, agents: dict[str, Any], tracer: Tracer, store: CheckpointStore,
                 retry: RetryManager, on_update: Callable[[RunState], None] | None = None):
        self.state, self.agents, self.tracer, self.store, self.retry = state, agents, tracer, store, retry
        self.on_update = on_update
        self.cancelled = False

    def _save(self) -> None:
        self.state.updated_at = now()
        self.store.save_state(self.state)
        self.tracer.flush()
        if self.on_update:
            self.on_update(self.state)

    def run(self, ctx: Any) -> RunState:
        st = self.state
        st.status = RunStatus.RUNNING
        self._save()
        max_steps = len(st.tasks) + 1        # hard guard: each task runs at most once per pass
        steps = 0
        for task in st.tasks:
            if self.cancelled:
                break
            if task.status in DONE:
                self.tracer.log(agent=task.agent, action="skip (checkpoint)", status=task.status.value,
                                task_id=task.task_id, tool=task.tool)
                continue
            steps += 1
            if steps > max_steps:
                raise RuntimeError("executor step limit exceeded")
            blocked = [d for d in task.depends_on if st.task(d).status not in DONE]
            if blocked:
                blocking_failed = [d for d in blocked if st.task(d).status == TaskStatus.FAILED]
                task.status = TaskStatus.NEEDS_REVIEW if not task.critical else TaskStatus.FAILED
                task.error = f"dependencies not completed: {blocked[:5]}"
                self.tracer.log(agent=task.agent, action="blocked", status=task.status.value, task_id=task.task_id,
                                tool=task.tool, detail=task.error)
                if task.critical and blocking_failed:
                    return self._fail(f"critical task {task.task_id} blocked by failures {blocking_failed[:3]}")
                continue
            self._execute(task, ctx)
            if task.status == TaskStatus.FAILED and task.critical:
                return self._fail(f"critical task {task.task_id} failed: {task.error}")
        if not self.cancelled:
            st.status = RunStatus.COMPLETED
            st.finished_at = now()
            st.stage = "done"
        self._save()
        return st

    def _execute(self, task: Task, ctx: Any) -> None:
        st = self.state
        st.stage = task.stage
        agent = self.agents[task.agent]
        task.status, task.started_at = TaskStatus.RUNNING, now()
        self.tracer.log(agent=task.agent, action="start", status="RUNNING", task_id=task.task_id, tool=task.tool)
        t0 = time.perf_counter()

        def on_retry(attempt: int, err: Exception) -> None:
            self.tracer.log(agent=task.agent, action="retry", status="RUNNING", task_id=task.task_id, tool=task.tool,
                            attempt=attempt, detail=str(err))

        try:
            out, attempts = self.retry.run(lambda a: agent.handle(task, ctx, self.tracer), task.max_retries, on_retry)
            task.attempts = attempts
            task.output = out or {}
            task.status = TaskStatus.NEEDS_REVIEW if (out or {}).get("needs_review") else TaskStatus.COMPLETED
        except Exception as e:
            task.attempts = getattr(e, "attempts", task.max_retries + 1)
            task.error = str(e)[:300]
            st.errors.append({"task_id": task.task_id, "error": task.error, "at": now()})
            if task.critical:
                task.status = TaskStatus.FAILED
            else:   # escalate to a human instead of failing the whole run
                task.status = TaskStatus.NEEDS_REVIEW
                st.escalations.append({"task_id": task.task_id, "reason": task.error})
        task.duration_ms = int((time.perf_counter() - t0) * 1000)
        task.finished_at = now()
        self.tracer.log(agent=task.agent, action="finish", status=task.status.value, task_id=task.task_id,
                        tool=task.tool, duration_ms=task.duration_ms, attempt=task.attempts,
                        detail=task.error or ", ".join(f"{k}={v}" for k, v in list((task.output or {}).items())[:4]))
        self._save()

    def _fail(self, msg: str) -> RunState:
        self.state.status = RunStatus.FAILED
        self.state.errors.append({"task_id": "run", "error": msg, "at": now()})
        self.state.finished_at = now()
        self._save()
        return self.state
