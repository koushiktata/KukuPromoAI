from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import settings
from ..src.shows import create_show, list_shows

router = APIRouter(prefix="/api/shows", tags=["shows"])
MAX_FILES = 300


@router.get("")
def shows():
    return {"shows": [{k: v for k, v in s.items() if k != "path"} for s in list_shows(settings)]}


@router.post("", status_code=201)
async def upload_show(name: str = Form(..., min_length=1, max_length=80), files: list[UploadFile] = File(...)):
    """Upload several episode screenplays as one new show."""
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"at most {MAX_FILES} files per show")
    payload = [(f.filename or "", await f.read(settings.max_upload_bytes + 1)) for f in files]
    res = create_show(settings, name, payload)
    if res["show"] is None:
        raise HTTPException(422, {"message": "none of the files is a usable timestamped screenplay",
                                  "rejected": res["rejected"]})
    res["show"] = {k: v for k, v in res["show"].items() if k != "path"}
    return res
