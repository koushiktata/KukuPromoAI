"""Shared singletons for the API (one DB + one orchestrator per process)."""
from __future__ import annotations

from functools import lru_cache

from ..agents.orchestrator import Orchestrator
from ..config import settings
from ..database import Database


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(settings.db_path)


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator(settings, get_db())


def current_data_dir():
    """Screenplay folder of the show behind the current results (latest completed run)."""
    from pathlib import Path
    run = get_db().latest_run(completed_only=True)
    d = (run or {}).get("config", {}).get("data_dir")
    return Path(d) if d and Path(d).exists() else settings.data_dir


def run_info(d: dict | None):
    from .schemas import RunInfo
    if not d:
        return None
    return RunInfo(run_id=d["run_id"], status=d["status"], stage=d.get("stage") or "", progress=d.get("progress") or 0,
                   counts=d.get("counts") or {}, metrics={k: v for k, v in (d.get("metrics") or {}).items()},
                   errors=d.get("errors") or [], created_at=d.get("created_at") or "",
                   finished_at=d.get("finished_at") or "", config=d.get("config") or {})
