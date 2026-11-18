#!/usr/bin/env python3
"""Organise each exported run folder into subfolders (parsed / candidates / cross_episode / ranked).
Files are moved or split from the run's own outputs; nothing is re-run or edited.

    python scripts/organize_run_folders.py
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path.home() / "Downloads" / "KukuPromoAI_raw_outputs"


def move(run: Path, name: str, sub: str) -> None:
    src = run / name
    if src.exists():
        (run / sub).mkdir(exist_ok=True)
        shutil.move(str(src), str(run / sub / name))


def organise(run: Path) -> dict:
    stats = {}
    # parsed/: events.csv (one row per timed line) + episodes.json (per-episode summary)
    parsed_path = run / "parsed_screenplays.json"
    if parsed_path.exists():
        parsed = json.loads(parsed_path.read_text())
        (run / "parsed").mkdir(exist_ok=True)
        with open(run / "parsed" / "events.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["episode", "event_id", "scene", "kind", "start_s", "end_s", "speaker", "emotions", "text",
                        "source_line"])
            n = 0
            for ep in parsed:
                for e in ep["events"]:
                    w.writerow([ep["episode"], e["event_id"], e["scene_id"], e["kind"], e["start"], e["end"],
                                e.get("speaker", ""), "; ".join(e.get("emotions") or []), e["text"], e["source_line"]])
                    n += 1
        (run / "parsed" / "episodes.json").write_text(json.dumps(
            [{"episode": ep["episode"], "file": ep["file"], "duration_s": ep["duration"], "logline": ep["logline"],
              "scenes": len(ep["scenes"]), "events": len(ep["events"])} for ep in parsed], indent=1))
        stats["events"] = n
    for f in ("parsed_screenplays.json", "data_inventory.json", "screenplay_format_report.md"):
        move(run, f, "parsed")

    # candidates/epNN.json (single-episode) and cross_episode/epNN-MM.json, each with its validation result
    cand_path = run / "candidate_moments.json"
    if cand_path.exists():
        cands = json.loads(cand_path.read_text())
        per_ep: dict[int, list] = {}
        cross: dict[str, list] = {}
        for p in cands:
            eps = sorted({s["episode"] for s in p["segments"]})
            slim = {k: p[k] for k in ("promo_id", "kind", "segments", "duration", "hook", "cliffhanger", "labels",
                                      "rule_hook", "rule_cliff", "rule_score", "scores", "validation") if k in p}
            if len(eps) == 1:
                per_ep.setdefault(eps[0], []).append(slim)
            else:
                cross.setdefault(f"ep{eps[0]:02d}-{eps[-1]:02d}", []).append(slim)
        (run / "candidates").mkdir(exist_ok=True)
        for n, items in sorted(per_ep.items()):
            (run / "candidates" / f"ep{n:02d}.json").write_text(json.dumps(
                {"episode": n, "candidates": len(items), "promos": items}, indent=1))
        if cross:
            (run / "cross_episode").mkdir(exist_ok=True)
            for key, items in sorted(cross.items()):
                (run / "cross_episode" / f"{key}.json").write_text(json.dumps(
                    {"episodes": key, "candidates": len(items), "promos": items}, indent=1))
        stats["episode_files"], stats["cross_files"] = len(per_ep), len(cross)
    for f in ("candidate_moments.json", "validated_promos.json"):
        move(run, f, "candidates")

    # ranked/
    for f in ("ranked.md", "ranked_promos.json", "ranked_promos.csv", "evaluation_results.csv"):
        move(run, f, "ranked")
    return stats


def main():
    runs = [d for d in sorted(DEST.iterdir()) if d.is_dir() and d.name[:2].isdigit()]
    for run in runs:
        print(run.name, organise(run))
    sys.path.insert(0, str(ROOT / "scripts"))
    from export_raw_outputs import write_readme_md
    write_readme_md(DEST)
    for junk in DEST.rglob(".DS_Store"):
        junk.unlink()
    print("zip:", shutil.make_archive(str(DEST), "zip", DEST.parent, DEST.name))


if __name__ == "__main__":
    main()
