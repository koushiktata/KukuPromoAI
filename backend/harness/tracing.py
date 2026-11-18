"""Execution trace: every agent step and tool call, with timing and status. No screenplay text, no keys."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable

from .state import now

log = logging.getLogger("kukupromo.trace")


class Tracer:
    def __init__(self, run_id: str, path: Path | None = None, sink: Callable[[dict], None] | None = None):
        self.run_id = run_id
        self.path = path
        self.sink = sink
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def log(self, *, agent: str, action: str, status: str, task_id: str = "", tool: str = "",
            duration_ms: int = 0, detail: str = "", attempt: int = 0) -> dict:
        ev = {"seq": len(self.events) + 1, "at": now(), "run_id": self.run_id, "task_id": task_id, "agent": agent,
              "action": action, "tool": tool, "status": status, "attempt": attempt,
              "duration_ms": duration_ms, "detail": detail[:300]}
        with self._lock:
            self.events.append(ev)
        log.info("[%s] %s %s %s %s", agent, action, tool, status, detail[:120])
        if self.sink:
            try:
                self.sink(ev)
            except Exception:   # tracing must never break the run
                log.exception("trace sink failed")
        return ev

    def flush(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.events, indent=1))

    def load(self, events: list[dict]) -> None:
        self.events = list(events)
