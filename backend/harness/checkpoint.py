"""JSON checkpoints: run state + per-task artifacts, so a run can resume where it stopped."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .state import RunState


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): _dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dump(v) for v in obj]
    return obj


class CheckpointStore:
    def __init__(self, root: Path):
        self.root = root

    def _dir(self, run_id: str) -> Path:
        d = self.root / run_id
        (d / "artifacts").mkdir(parents=True, exist_ok=True)
        return d

    def save_state(self, state: RunState) -> None:
        p = self._dir(state.run_id) / "state.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(state.model_dump_json(indent=1))
        tmp.replace(p)                     # atomic: a crash never leaves half a checkpoint

    def load_state(self, run_id: str) -> RunState | None:
        p = self.root / run_id / "state.json"
        return RunState.model_validate_json(p.read_text()) if p.exists() else None

    def save_artifact(self, run_id: str, key: str, obj: Any) -> None:
        p = self._dir(run_id) / "artifacts" / f"{key}.json"
        p.write_text(json.dumps(_dump(obj)))

    def load_artifact(self, run_id: str, key: str) -> Any | None:
        p = self.root / run_id / "artifacts" / f"{key}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in self.root.glob("*") if (p / "state.json").exists())
