from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import settings
from ..src.models import Promo
from ..src.validation import validate_promo
from ..tools.workspace import Workspace
from .deps import current_data_dir, get_db
from .schemas import ReviewRequest

router = APIRouter(prefix="/api/promos", tags=["promos"])


@router.get("")
def list_promos(category: Literal["all", "new_viewer", "retarget", "neither"] = "all",
                decision: Literal["all", "not_reviewed", "approved", "rejected"] = "all",
                status: Literal["all", "VALID", "NEEDS_REVIEW", "INVALID"] = "all",
                min_score: float = Query(0, ge=0, le=5), episode: int | None = None,
                include_unranked: bool = False, db=Depends(get_db)):
    out = []
    for p in db.promos():
        if not include_unranked and not p.get("rank"):
            continue
        cat = p["category"]
        if category == "new_viewer" and not cat["new_viewer"]:
            continue
        if category == "retarget" and not cat["retarget"]:
            continue
        if category == "neither" and (cat["new_viewer"] or cat["retarget"]):
            continue
        if decision != "all" and p["review"]["decision"] != decision:
            continue
        if status != "all" and p["validation"]["status"] != status:
            continue
        if p["scores"]["overall"] < min_score:
            continue
        if episode is not None and all(s["episode"] != episode for s in p["segments"]):
            continue
        out.append(p)
    counts = {"new_viewer": sum(p["category"]["new_viewer"] for p in db.promos() if p.get("rank")),
              "retarget": sum(p["category"]["retarget"] for p in db.promos() if p.get("rank"))}
    return {"count": len(out), "category_counts": counts, "promos": out}


@router.get("/{promo_id}")
def get_promo(promo_id: str, include_transcript: bool = False, db=Depends(get_db)):
    p = db.promo(promo_id)
    if not p:
        raise HTTPException(404, "promo not found")
    p["review_history"] = db.review_history(promo_id)
    flags = {f["flag_id"]: f for f in db.flags()}
    p["content_flags"] = [flags[f] for f in p.get("content_flag_ids", []) if f in flags]
    secrets = {s["secret_id"]: s for s in db.secrets()}
    p["spoilers"] = [{"secret_id": s, "theme": secrets[s]["theme"], "severity": secrets[s]["severity"],
                      "review": secrets[s]["review"]["status"]} for s in p["category"]["spoiler_secret_ids"] if s in secrets]
    if include_transcript:
        ws = Workspace("api", current_data_dir(), settings.output_dir, None, None, {})
        lines = []
        for s in p["segments"]:
            try:
                ep = ws.episode(s["episode"])
            except KeyError:
                continue
            lines.append({"segment": s["order"], "episode": s["episode"], "lines": [
                {"ts": f"{e.start:.2f}", "kind": e.kind, "who": e.label(), "text": e.text}
                for e in ep.events if s["start"] - 1e-6 <= e.start < s["end"] - 1e-6]})
        p["transcript"] = lines
    return p


@router.post("/{promo_id}/validate")
def revalidate(promo_id: str, db=Depends(get_db)):
    p = db.promo(promo_id)
    if not p:
        raise HTTPException(404, "promo not found")
    ws = Workspace("api", current_data_dir(), settings.output_dir, None, None, {})
    promo = Promo.model_validate({k: v for k, v in p.items() if k not in ("review",)})
    try:
        eps = {s.episode: ws.episode(s.episode) for s in promo.segments}
    except KeyError as e:
        raise HTTPException(409, f"source screenplay missing: {e}")
    v = validate_promo(promo, eps, min_s=settings.promo_min_s, max_s=settings.promo_max_s,
                       hook_window=settings.hook_window_s)
    return {"promo_id": promo_id, "stored_status": p["validation"]["status"], "status": v.status.value,
            "checks": [c.model_dump() for c in v.checks], "consistent": v.status.value == p["validation"]["status"]}


@router.post("/{promo_id}/review")
def review(promo_id: str, req: ReviewRequest, db=Depends(get_db)):
    if not db.promo(promo_id):
        raise HTTPException(404, "promo not found")
    saved = db.set_review(promo_id, req.decision, req.reason.strip(), req.reviewer.strip())
    return {"review": saved, "stats": db.review_stats()}
