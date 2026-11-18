from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from ..config import settings
from ..src import reports
from .deps import get_db, run_info
from .schemas import Summary

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/summary", response_model=Summary)
def summary(db=Depends(get_db)):
    run = db.latest_run()
    done = db.latest_run(completed_only=True)
    m = (done or {}).get("metrics", {})
    promos = [p for p in db.promos() if p.get("rank")]
    secrets, flags = db.secrets(), db.flags()
    used = {f for p in promos for f in p.get("content_flag_ids", [])}
    flags_used = [f for f in flags if f["flag_id"] in used]
    unrev = [f for f in flags_used if f["review"]["status"] in ("unreviewed", "needs_review")]
    sec_unver = sum(s["review"]["status"] in ("unreviewed", "needs_review") for s in secrets)
    cfg = (done or {}).get("config", {})
    return Summary(
        run=run_info(run), show_name=cfg.get("show_name", ""), show_id=cfg.get("show", ""),
        judges=cfg.get("providers") or [cfg.get("provider", "mock")],
        episodes=m.get("episodes", len(db.episodes())),
        candidates=m.get("candidates", db.candidate_count(done["run_id"]) if done else 0),
        passed_rules=m.get("candidates_valid", 0), ranked=len(promos),
        new_viewer=sum(p["category"]["new_viewer"] for p in promos),
        retarget=sum(p["category"]["retarget"] for p in promos),
        processing_seconds=m.get("wall_seconds", m.get("processing_seconds")),
        review=db.review_stats(), secrets_total=len(secrets), secrets_unverified=sec_unver,
        flags_total=len(flags_used), flags_unreviewed=len(unrev),
        high_severity_flags_unreviewed=sum(f["severity"] == "high" for f in unrev),
        posting_warning=bool(unrev or sec_unver))


@router.get("/approved")
def approved(fmt: str = Query("csv", pattern="^(csv|json)$"), db=Depends(get_db)):
    rows = [reports.flat_row(p) for p in db.promos() if p.get("rank") and p["review"]["decision"] == "approved"]
    if fmt == "json":
        return Response(json.dumps({"count": len(rows), "promos": rows}, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="approved_promos.json"', "X-Row-Count": str(len(rows))})
    return Response(reports.to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="approved_promos.csv"', "X-Row-Count": str(len(rows))})


@router.get("/all-decisions")
def all_decisions(db=Depends(get_db)):
    rows = [reports.flat_row(p) for p in db.promos() if p.get("rank")]
    return Response(reports.to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="all_promos_decisions.csv"', "X-Row-Count": str(len(rows))})


@router.get("/full", response_class=PlainTextResponse)
def full(db=Depends(get_db)):
    run = db.latest_run(completed_only=True)
    if not run:
        raise HTTPException(404, "no completed run yet")
    md = reports.markdown_report(db.promos(), db.secrets(), db.flags(), db.review_stats(), run,
                                 show=run.get("config", {}).get("show_name", ""))
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": 'attachment; filename="ranked.md"'})


@router.get("/evaluation")
def evaluation(db=Depends(get_db)):
    p = settings.output_dir / "evaluation_summary.json"
    if not p.exists():
        raise HTTPException(404, "no evaluation yet - run the pipeline first")
    data = json.loads(p.read_text())
    data["review"] = db.review_stats()
    return data


@router.get("/file/{name}")
def output_file(name: str):
    allowed = {"ranked_promos.json", "evaluation_results.csv", "agent_execution_trace.json", "agent_run_summary.json",
               "processing_report.json", "data_inventory.json", "screenplay_format_report.md"}
    if name not in allowed:
        raise HTTPException(404, "unknown file")
    p = settings.output_dir / name
    if not p.exists():
        raise HTTPException(404, "file not generated yet")
    media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else "text/markdown"
    return Response(p.read_text(), media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
