from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..config import settings
from ..src.parser import parse_text
from .deps import current_data_dir, get_db

router = APIRouter(prefix="/api/episodes", tags=["episodes"])
NAME_RE = re.compile(r"^[\w .()\-]+\.txt$")


@router.get("")
def list_episodes(db=Depends(get_db)):
    files = sorted(p.name for p in current_data_dir().glob("*.txt"))
    parsed = db.episodes()
    nums = [e["episode"] for e in parsed]
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    return {"files_found": len(files), "processed": len(parsed), "missing": missing,
            "episodes": [{k: v for k, v in e.items() if k != "sha1"} for e in parsed]}


@router.get("/{episode_id}")
def get_episode(episode_id: int, db=Depends(get_db)):
    ep = next((e for e in db.episodes() if e["episode"] == episode_id), None)
    if not ep:
        raise HTTPException(404, f"episode {episode_id} not processed yet")
    promos = [{"promo_id": p["promo_id"], "rank": p.get("rank"), "overall": p["scores"]["overall"]}
              for p in db.promos() if any(s["episode"] == episode_id for s in p["segments"])]
    flags = [f for f in db.flags() if f["episode"] == episode_id]
    return {**{k: v for k, v in ep.items() if k != "sha1"}, "promos": promos, "content_flags": len(flags)}


@router.post("/upload", status_code=201)
async def upload(files: list[UploadFile] = File(...)):
    saved, rejected = [], []
    for f in files:
        name = (f.filename or "").split("/")[-1]
        if not NAME_RE.match(name):
            rejected.append({"file": name, "reason": "only .txt screenplay files with simple names"})
            continue
        data = await f.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            rejected.append({"file": name, "reason": f"larger than {settings.max_upload_bytes // 1024} KB"})
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            rejected.append({"file": name, "reason": "not UTF-8 text"})
            continue
        ep = parse_text(text, name)
        if not ep.events or not ep.number:
            rejected.append({"file": name, "reason": "no timed screenplay events / episode number found"})
            continue
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / name).write_text(text)
        saved.append({"file": name, "episode": ep.number, "events": len(ep.events), "issues": ep.issues})
    if not saved and rejected:
        raise HTTPException(422, {"saved": [], "rejected": rejected})
    return {"saved": saved, "rejected": rejected}
