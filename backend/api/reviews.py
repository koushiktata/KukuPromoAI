"""Secrets + content flags (human verification)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from .deps import get_db
from .schemas import VerifyRequest

router = APIRouter(prefix="/api", tags=["secrets & content flags"])


@router.get("/secrets")
def secrets(db=Depends(get_db)):
    items = db.secrets()
    return {"ai_generated": True,
            "disclaimer": "AI-generated from screenplay evidence. May be incomplete or wrong - verify before relying on it.",
            "count": len(items), "unverified": sum(s["review"]["status"] in ("unreviewed", "needs_review") for s in items),
            "secrets": items}


@router.post("/secrets/{secret_id}/review")
def review_secret(secret_id: str, req: VerifyRequest, db=Depends(get_db)):
    if not any(s["secret_id"] == secret_id for s in db.secrets()):
        raise HTTPException(404, "secret not found")
    return db.set_secret_review(secret_id, req.status, req.note.strip(), req.reviewer.strip())


@router.get("/content-flags")
def flags(severity: Literal["all", "low", "medium", "high"] = "all",
          status: Literal["all", "unreviewed", "verified", "incorrect", "needs_review"] = "all",
          in_ranked_promos: bool = False, db=Depends(get_db)):
    items = db.flags()
    if in_ranked_promos:
        used = {f for p in db.promos() if p.get("rank") for f in p.get("content_flag_ids", [])}
        items = [f for f in items if f["flag_id"] in used]
    if severity != "all":
        items = [f for f in items if f["severity"] == severity]
    if status != "all":
        items = [f for f in items if f["review"]["status"] == status]
    return {"disclaimer": "Content-review signals, not legal or platform-policy decisions. "
                          "No flag does not mean a promo is safe.",
            "count": len(items), "flags": items}


@router.post("/content-flags/{flag_id}/review")
def review_flag(flag_id: str, req: VerifyRequest, db=Depends(get_db)):
    if not any(f["flag_id"] == flag_id for f in db.flags()):
        raise HTTPException(404, "flag not found")
    return db.set_flag_review(flag_id, req.status, req.note.strip(), req.reviewer.strip())
