"""Registered tools with Pydantic input/output schemas, error handling and logging."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

log = logging.getLogger("kukupromo.tools")


class ToolError(Exception):
    def __init__(self, tool: str, message: str, retryable: bool = True):
        super().__init__(f"{tool}: {message}")
        self.tool, self.retryable = tool, retryable


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    fn: Callable[[Any, BaseModel], BaseModel | dict]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, input_model: type[BaseModel], output_model: type[BaseModel]):
        def deco(fn):
            if name in self._tools:
                raise ValueError(f"tool {name} already registered")
            self._tools[name] = Tool(name, description, input_model, output_model, fn)
            return fn
        return deco

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(name, "unknown tool", retryable=False)
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict]:
        return [{"name": t.name, "description": t.description,
                 "input_schema": t.input_model.model_json_schema(),
                 "output_schema": t.output_model.model_json_schema()} for t in self._tools.values()]

    def call(self, name: str, args: dict | None, ctx: Any) -> BaseModel:
        tool = self.get(name)
        try:
            inp = tool.input_model(**(args or {}))
        except ValidationError as e:
            raise ToolError(name, f"invalid input: {e.errors()[:2]}", retryable=False) from e
        t0 = time.perf_counter()
        try:
            raw = tool.fn(ctx, inp)
        except ToolError:
            raise
        except Exception as e:  # wrap anything unexpected
            log.warning("tool %s failed: %s", name, e)
            raise ToolError(name, f"{type(e).__name__}: {e}") from e
        try:
            out = raw if isinstance(raw, tool.output_model) else tool.output_model.model_validate(raw)
        except ValidationError as e:
            raise ToolError(name, f"invalid output: {e.errors()[:2]}", retryable=False) from e
        log.debug("tool %s ok in %.0fms", name, (time.perf_counter() - t0) * 1000)
        return out
