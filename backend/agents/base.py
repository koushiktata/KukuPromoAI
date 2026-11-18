"""Base agent: a named role that executes its tasks through registered tools (and only tools)."""
from __future__ import annotations

import time

from ..harness.state import Task
from ..harness.tool_registry import ToolRegistry
from ..harness.tracing import Tracer


class BaseAgent:
    name = "agent"
    role = ""
    allowed_tools: tuple[str, ...] = ()

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def call_tool(self, tool: str, args: dict, ws, tracer: Tracer, task_id: str = "") -> dict:
        if self.allowed_tools and tool not in self.allowed_tools:
            raise PermissionError(f"{self.name} may not call {tool}")
        t0 = time.perf_counter()
        try:
            out = self.registry.call(tool, args, ws).model_dump()
        except Exception as e:
            tracer.log(agent=self.name, action="tool_call", tool=tool, status="ERROR", task_id=task_id,
                       duration_ms=int((time.perf_counter() - t0) * 1000), detail=str(e))
            raise
        summary = ", ".join(f"{k}={v}" for k, v in out.items() if isinstance(v, (int, float, str, bool)))[:200]
        tracer.log(agent=self.name, action="tool_call", tool=tool, status="OK", task_id=task_id,
                   duration_ms=int((time.perf_counter() - t0) * 1000), detail=summary)
        return out

    def handle(self, task: Task, ws, tracer: Tracer) -> dict:
        return self.call_tool(task.tool, task.args, ws, tracer, task.task_id)
