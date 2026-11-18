"""save_results: write every output file and persist to SQLite."""
from __future__ import annotations

import json
import time

from pydantic import BaseModel

from ..harness.tool_registry import ToolRegistry
from ..src import evaluation, reports
from ..src.ingestion import format_report, inventory
from .screenplay_tools import Empty


class SaveOut(BaseModel):
    files: list[str]
    ranked: int
    promos_in_db: int


def register(reg: ToolRegistry) -> None:
    @reg.register("save_results", "Write outputs/*.json|csv|md and persist results to SQLite", Empty, SaveOut)
    def save_results(ws, _):
        out = ws.output_dir
        out.mkdir(parents=True, exist_ok=True)
        eps = ws.episodes()
        ws.load_promos()
        ws.load_ranked()
        ws.load_secrets_flags()
        if not ws.ranked:
            raise RuntimeError("nothing ranked to save")
        inv = inventory(list(eps.values()), ws.data_dir)
        files = {}

        def write(name, text):
            (out / name).write_text(text)
            files[name] = True

        write("data_inventory.json", json.dumps(inv, indent=2))
        write("screenplay_format_report.md", format_report(list(eps.values()), inv))
        write("parsed_screenplays.json", json.dumps(
            [{"episode": e.number, "file": e.file_name, "duration": e.duration, "logline": e.logline,
              "scenes": [s.model_dump() for s in e.scenes],
              "events": [ev.model_dump() for ev in e.events]} for e in eps.values()]))
        write("candidate_moments.json", json.dumps([p.model_dump(mode="json") for p in ws.promos]))
        write("validated_promos.json", json.dumps(
            [{"promo_id": p.promo_id, "status": p.validation.status.value,
              "checks": [c.model_dump() for c in p.validation.checks]} for p in ws.promos], indent=1))
        ranked_dicts = [p.model_dump(mode="json") for p in ws.ranked]
        write("ranked_promos.json", json.dumps(ranked_dicts, indent=1))
        rows = [reports.flat_row({**d, "review": {}}) for d in ranked_dicts]
        write("ranked_promos.csv", reports.to_csv(rows))
        ev_rows = evaluation.promo_rows(ws.ranked)
        write("evaluation_results.csv", reports.to_csv(ev_rows))
        run_state = ws.store.load_state(ws.run_id)
        started = run_state.created_at if run_state else ""
        secs = time.time() - getattr(ws, "t0", time.time())
        summ = evaluation.summary(ws.promos, ws.ranked, eps, ws.secrets, ws.flags, secs, ws.llm.name)
        ws.metrics = summ
        write("evaluation_summary.json", json.dumps(summ, indent=2))
        write("processing_report.json", json.dumps({
            "run_id": ws.run_id, "started_at": started, "show": getattr(ws, "show_name", ws.data_dir.name),
            "files_found": inv["files_found"], "episodes_processed": len(eps),
            "missing_episodes": inv["missing_episodes"], "parser_issues": {e.number: e.issues for e in eps.values() if e.issues},
            "provider": ws.llm.name, "metrics": {k: v for k, v in summ.items() if k != "reference"}}, indent=2))
        # persist
        if ws.db:
            ws.db.replace_results(
                ws.run_id,
                episodes=[{"episode": e["episode"], "file_name": e["file"], "sha1": eps[e["episode"]].sha1,
                           "duration": e["duration_s"], "scenes": e["scenes"], "events": e["events"],
                           "dialogue": e["dialogue_lines"], "logline": eps[e["episode"]].logline, "issues": e["issues"]}
                          for e in inv["episodes"]],
                candidates=[p.model_dump(mode="json") for p in ws.promos], promos=ranked_dicts,
                secrets=[s.model_dump() for s in ws.secrets], flags=[f.model_dump() for f in ws.flags])
            stats = ws.db.review_stats()
            md = reports.markdown_report(ws.db.promos(), ws.db.secrets(), ws.db.flags(), stats,
                                         {"run_id": ws.run_id, "metrics": summ}, show=getattr(ws, "show_name", ws.data_dir.name))
        else:
            md = reports.markdown_report([{**d, "review": {}} for d in ranked_dicts], [s.model_dump() for s in ws.secrets],
                                         [f.model_dump() for f in ws.flags],
                                         {"reviewed": 0, "total": len(ranked_dicts), "approved": 0, "rejected": 0,
                                          "approval_rate": None}, {"run_id": ws.run_id, "metrics": summ})
        write("ranked.md", md)
        return SaveOut(files=sorted(files), ranked=summ["ranked"], promos_in_db=len(ranked_dicts))


def build_registry():
    from ..harness.tool_registry import ToolRegistry
    from . import promo_tools, review_tools, screenplay_tools
    reg = ToolRegistry()
    screenplay_tools.register(reg)
    promo_tools.register(reg)
    review_tools.register(reg)
    register(reg)
    return reg
