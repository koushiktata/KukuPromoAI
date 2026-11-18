"""Shows = folders of episode screenplays. 'default' is KUKU_DATA_DIR; each upload becomes data/shows/<id>/."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .parser import parse_text

NAME_RE = re.compile(r"^[\w .()\-]+\.txt$")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "show")[:48]


def list_shows(settings) -> list[dict]:
    out = []
    if settings.data_dir.exists():
        out.append(_info("default", settings.data_dir, {"name": settings.data_dir.name.replace("scripts", "Default show")
                                                        if settings.data_dir.name == "scripts" else settings.data_dir.name}))
    if settings.shows_dir.exists():
        for d in sorted(settings.shows_dir.iterdir()):
            if d.is_dir():
                meta = {}
                if (d / "show.json").exists():
                    try:
                        meta = json.loads((d / "show.json").read_text())
                    except ValueError:
                        meta = {}
                out.append(_info(d.name, d, meta))
    return out


def _info(show_id: str, path: Path, meta: dict) -> dict:
    files = sorted(path.glob("*.txt"))
    return {"show_id": show_id, "name": meta.get("name") or show_id, "files": len(files),
            "created_at": meta.get("created_at", ""), "path": str(path)}


def resolve_show(settings, show_id: str | None) -> Path:
    if not show_id or show_id == "default":
        return settings.data_dir
    if not re.fullmatch(r"[a-z0-9\-]{1,64}", show_id):
        raise KeyError(show_id)
    p = settings.shows_dir / show_id
    if not p.is_dir():
        raise KeyError(show_id)
    return p


def validate_upload(filename: str, data: bytes, max_bytes: int) -> tuple[str | None, dict]:
    """Returns (text, info) when the file is a usable screenplay, else (None, {reason})."""
    name = (filename or "").split("/")[-1]
    if not NAME_RE.match(name):
        return None, {"file": name, "reason": "only .txt screenplay files with simple names"}
    if len(data) > max_bytes:
        return None, {"file": name, "reason": f"larger than {max_bytes // 1024} KB"}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, {"file": name, "reason": "not UTF-8 text"}
    ep = parse_text(text, name)
    if not ep.events or not ep.number:
        return None, {"file": name, "reason": "no timed screenplay events / episode number found"}
    return text, {"file": name, "episode": ep.number, "events": len(ep.events), "issues": ep.issues}


def create_show(settings, name: str, files: list[tuple[str, bytes]]) -> dict:
    saved, rejected, texts = [], [], []
    for fname, data in files:
        text, info = validate_upload(fname, data, settings.max_upload_bytes)
        (saved if text else rejected).append(info)
        if text:
            texts.append((info["file"], text))
    if not texts:
        return {"show": None, "saved": [], "rejected": rejected}
    eps = [s["episode"] for s in saved]
    dup = sorted({e for e in eps if eps.count(e) > 1})
    base = slugify(name)
    show_id, i = base, 2
    while (settings.shows_dir / show_id).exists():
        show_id, i = f"{base}-{i}", i + 1
    d = settings.shows_dir / show_id
    d.mkdir(parents=True)
    for fname, text in texts:
        (d / fname).write_text(text)
    (d / "show.json").write_text(json.dumps({"name": name.strip() or show_id,
                                             "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    return {"show": _info(show_id, d, {"name": name.strip() or show_id}), "saved": saved, "rejected": rejected,
            "duplicate_episode_numbers": dup}
