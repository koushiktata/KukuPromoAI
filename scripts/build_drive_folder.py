#!/usr/bin/env python3
"""Assemble the ready-to-upload Drive folder from the latest exports.

    python scripts/build_drive_folder.py

Creates ~/Downloads/KukuPromoAI_Drive_Upload/:
  1_Solution_Doc.pdf  2_Prototype_Links.txt  Raw_Outputs/  Video/
The source folders (KukuPromoAI_raw_outputs, docs/) are left untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DL = Path.home() / "Downloads"
SRC_RAW = DL / "KukuPromoAI_raw_outputs"
DEST = DL / "KukuPromoAI_Drive_Upload"
RENAME = {"01_full_show_rules_only": "01_full_run_50_episodes",
          "02_episodes_1-10_groq_judge": "02_groq_judge_episodes_1-10"}


def main():
    if not SRC_RAW.is_dir():
        sys.exit(f"{SRC_RAW} not found: run scripts/export_raw_outputs.py first")
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir()
    shutil.copy2(ROOT / "docs" / "KukuPromoAI_solution.pdf", DEST / "1_Solution_Doc.pdf")
    links = DL / "2_Prototype_Links.txt"
    if links.exists():
        shutil.copy2(links, DEST / "2_Prototype_Links.txt")

    raw = DEST / "Raw_Outputs"
    shutil.copytree(SRC_RAW, raw, ignore=shutil.ignore_patterns(".DS_Store"))
    for old, new in RENAME.items():
        if (raw / old).exists():
            (raw / old).rename(raw / new)
    ev = raw / "evaluation"
    ev.mkdir(exist_ok=True)
    for f in ("benchmark/benchmark.md", "benchmark/benchmark.json", "reference_moments.json", "runs.json"):
        if (raw / f).exists():
            shutil.move(str(raw / f), str(ev / Path(f).name))
    shutil.rmtree(raw / "benchmark", ignore_errors=True)
    runs_json = ev / "runs.json"
    if runs_json.exists():
        txt = runs_json.read_text()
        for old, new in RENAME.items():
            txt = txt.replace(old, new)
        runs_json.write_text(txt)

    sys.path.insert(0, str(ROOT / "scripts"))
    from export_raw_outputs import write_readme_md
    write_readme_md(raw)

    video = DEST / "Video"
    video.mkdir()
    (video / "ADD_YOUR_VIDEO_HERE.txt").write_text(
        "Put your walkthrough video here (up to 3 minutes, screen recording in your own voice),\n"
        "or a link to it (Loom / unlisted YouTube). Plan: docs/demo_script.md in the project.\n"
        "Delete this note after adding the video.\n")
    n = sum(1 for _ in DEST.rglob("*") if _.is_file())
    print(f"{DEST}  ({n} files)")


if __name__ == "__main__":
    main()
