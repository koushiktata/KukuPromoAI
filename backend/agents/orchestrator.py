"""Orchestrator: plan -> execute (with retries, checkpoints, tracing) -> persist. Supports resume."""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime

from ..config import Settings, settings as default_settings
from ..database import Database
from ..harness.checkpoint import CheckpointStore
from ..harness.executor import Executor
from ..harness.planner import OBJECTIVE, build_plan
from ..harness.retry_manager import RetryManager
from ..harness.state import RunState, RunStatus, TaskStatus
from ..harness.tracing import Tracer
from pathlib import Path

from ..llm.configurable_provider import make_providers
from ..src.shows import list_shows, resolve_show
from ..tools.output_tools import build_registry
from ..tools.workspace import Workspace
from .agents import build_agents

log = logging.getLogger("kukupromo.orchestrator")


class Orchestrator:
    def __init__(self, cfg: Settings | None = None, db: Database | None = None):
        self.cfg = cfg or default_settings
        self.db = db or Database(self.cfg.db_path)
        self.store = CheckpointStore(self.cfg.checkpoint_dir)
        self.registry = build_registry()
        self.agents = build_agents(self.registry)
        self._threads: dict[str, threading.Thread] = {}
        self._executors: dict[str, Executor] = {}
        self.recover_interrupted()

    def recover_interrupted(self) -> list[str]:
        """A run still marked RUNNING when this process starts was cut off (e.g. the backend restarted).
        Mark it FAILED so the UI unlocks; its checkpoint lets the user resume it."""
        fixed = []
        for r in self.db.list_runs(100):
            if r["status"] != RunStatus.RUNNING.value:
                continue
            st = self.store.load_state(r["run_id"])
            if st is None:
                continue
            for t in st.tasks:
                if t.status == TaskStatus.RUNNING:
                    t.status = TaskStatus.PENDING
            st.status = RunStatus.FAILED
            st.errors.append({"task_id": "run", "error": "interrupted: the backend restarted during this run. "
                                                         "Resume it from its checkpoint or start a new run."})
            self.store.save_state(st)
            self.db.upsert_run(st)
            fixed.append(st.run_id)
            log.warning("marked interrupted run %s as FAILED (resumable)", st.run_id)
        return fixed

    # ---------- lifecycle ----------
    def create_run(self, episodes: list[int] | None = None, options: dict | None = None) -> RunState:
        opts = options or {}
        show_id = opts.get("show") or "default"
        data_dir = resolve_show(self.cfg, show_id)            # KeyError for an unknown show
        files = Workspace("probe", data_dir, self.cfg.output_dir, self.store, None, {}).scan_files()
        if not files:
            raise FileNotFoundError(f"no screenplay .txt files in show '{show_id}'")
        ids = sorted(n for n in files if not episodes or n in episodes)
        if not ids:
            raise FileNotFoundError("none of the requested episodes exist in this show")
        run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        providers = opts.get("providers") or [opts.get("provider") or self.cfg.llm_provider]
        show_name = next((s["name"] for s in list_shows(self.cfg) if s["show_id"] == show_id), show_id)
        st = RunState(run_id=run_id, objective=OBJECTIVE,
                      config={"episodes": ids, "show": show_id, "show_name": show_name, "data_dir": str(data_dir),
                              "providers": providers, "provider": "+".join(providers),
                              "models": opts.get("models") or ({providers[0]: opts["model"]} if opts.get("model") else {}),
                              "max_retries": int(opts.get("max_retries", self.cfg.max_retries)),
                              "weights": opts.get("weights", self.cfg.weights)},
                      tasks=build_plan(ids, int(opts.get("max_retries", self.cfg.max_retries))))
        self.store.save_state(st)
        self.db.upsert_run(st)
        return st

    def _workspace(self, st: RunState) -> Workspace:
        cfg = Settings()
        providers = st.config.get("providers") or [st.config.get("provider") or cfg.llm_provider]
        llm = make_providers(cfg, providers, st.config.get("models") or {})
        data_dir = Path(st.config.get("data_dir") or self.cfg.data_dir)
        ws = Workspace(st.run_id, data_dir, self.cfg.output_dir, self.store, llm,
                       st.config.get("weights") or self.cfg.weights, db=self.db, episode_ids=st.config["episodes"])
        ws.show_name = st.config.get("show_name") or data_dir.name
        ws.t0 = time.time()
        return ws

    def execute(self, run_id: str) -> RunState:
        st = self.store.load_state(run_id)
        if st is None:
            raise KeyError(run_id)
        tracer = Tracer(run_id, self.cfg.checkpoint_dir / run_id / "trace.json", sink=self.db.add_trace)
        tracer.load(self.db.traces(run_id))
        try:
            ws = self._workspace(st)
        except Exception as e:      # e.g. missing API key for the chosen provider
            st.status = RunStatus.FAILED
            st.errors.append({"task_id": "setup", "error": str(e)})
            self.store.save_state(st)
            self.db.upsert_run(st)
            return st
        tracer.log(agent="orchestrator", action="plan", status="OK",
                   detail=f"{len(st.tasks)} tasks · provider {ws.llm.name} · resume={st.status != RunStatus.NOT_STARTED}")
        ex = Executor(st, self.agents, tracer, self.store, RetryManager(st.config.get("max_retries", 2)),
                      on_update=self.db.upsert_run)
        self._executors[run_id] = ex
        st = ex.run(ws)
        st.metrics = getattr(ws, "metrics", st.metrics) or st.metrics
        st.metrics["wall_seconds"] = round(time.time() - ws.t0, 1)
        st.metrics["task_counts"] = st.counts()
        self.store.save_state(st)
        self.db.upsert_run(st)
        self._write_run_files(st, tracer)
        return st

    def _write_run_files(self, st: RunState, tracer: Tracer) -> None:
        out = self.cfg.output_dir
        out.mkdir(parents=True, exist_ok=True)
        (out / "agent_execution_trace.json").write_text(json.dumps(tracer.events, indent=1))
        by_agent: dict[str, dict] = {}
        for t in st.tasks:
            a = by_agent.setdefault(t.agent, {"tasks": 0, "completed": 0, "needs_review": 0, "failed": 0,
                                              "retries": 0, "ms": 0})
            a["tasks"] += 1
            a["completed"] += t.status == TaskStatus.COMPLETED
            a["needs_review"] += t.status == TaskStatus.NEEDS_REVIEW
            a["failed"] += t.status == TaskStatus.FAILED
            a["retries"] += max(0, t.attempts - 1)
            a["ms"] += t.duration_ms
        (out / "agent_run_summary.json").write_text(json.dumps({
            "run_id": st.run_id, "objective": st.objective, "status": st.status.value,
            "created_at": st.created_at, "finished_at": st.finished_at, "task_counts": st.counts(),
            "agents": by_agent, "errors": st.errors, "escalations": st.escalations,
            "metrics": {k: v for k, v in st.metrics.items() if k != "reference"}}, indent=2))

    # ---------- background ----------
    def start_async(self, episodes=None, options=None) -> RunState:
        if self.running():
            raise RuntimeError("a run is already in progress")
        st = self.create_run(episodes, options)
        self._spawn(st.run_id)
        return st

    def resume_async(self, run_id: str) -> RunState:
        st = self.store.load_state(run_id)
        if st is None:
            raise KeyError(run_id)
        if st.status == RunStatus.COMPLETED:
            raise ValueError("run already completed")
        if self.running():
            raise RuntimeError("a run is already in progress")
        for t in st.tasks:              # targeted retry: only unfinished / failed tasks run again
            if t.status in (TaskStatus.FAILED, TaskStatus.RUNNING):
                t.status, t.error = TaskStatus.PENDING, ""
        st.status = RunStatus.RUNNING
        st.errors = [e for e in st.errors if e.get("task_id") != "run"]
        self.store.save_state(st)
        self.db.upsert_run(st)
        self._spawn(run_id)
        return st

    def _spawn(self, run_id: str) -> None:
        def target():
            try:
                self.execute(run_id)
            except Exception:
                log.exception("run %s crashed", run_id)
                st = self.store.load_state(run_id)
                if st:
                    st.status = RunStatus.FAILED
                    st.errors.append({"task_id": "run", "error": "orchestrator crashed - see server log"})
                    self.store.save_state(st)
                    self.db.upsert_run(st)
        th = threading.Thread(target=target, name=run_id, daemon=True)
        self._threads[run_id] = th
        th.start()

    def running(self) -> str | None:
        return next((rid for rid, th in self._threads.items() if th.is_alive()), None)

    def state(self, run_id: str) -> RunState | None:
        return self.store.load_state(run_id)
