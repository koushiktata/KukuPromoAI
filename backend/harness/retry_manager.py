"""Bounded retries for a single task (targeted retry - never restarts the whole dataset)."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from .tool_registry import ToolError

T = TypeVar("T")


class RetryManager:
    def __init__(self, max_retries: int = 2, backoff_s: float = 0.5, sleep=time.sleep):
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.sleep = sleep

    def run(self, fn: Callable[[int], T], max_retries: int | None = None,
            on_retry: Callable[[int, Exception], None] | None = None) -> tuple[T, int]:
        """Call fn(attempt). Returns (result, attempts). Raises the last error after max_retries retries."""
        limit = self.max_retries if max_retries is None else max_retries
        attempt = 0
        while True:
            attempt += 1
            try:
                return fn(attempt), attempt
            except Exception as e:
                retryable = not (isinstance(e, ToolError) and not e.retryable)
                if not retryable or attempt > limit:
                    e.attempts = attempt          # type: ignore[attr-defined]
                    raise
                if on_retry:
                    on_retry(attempt, e)
                self.sleep(self.backoff_s * attempt)
