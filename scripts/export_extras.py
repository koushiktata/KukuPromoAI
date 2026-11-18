#!/usr/bin/env python3
"""Add supporting files to an existing raw-outputs export (run after export_raw_outputs.py).

    python scripts/export_extras.py

Adds, all generated from this project:
  show_secrets_and_flags/   the show's secrets (with evidence) + content flags (deterministic, same as the run)
  all_ai_calls_unedited/    every LLM judge reply from the LLM run, one JSON line per call, unedited
  01_*/run.log              human-readable log of the full run (from the agent trace)
  01_*/baselines/           tool vs simple baselines on the 8 reference moments
Then rewrites README.md and re-zips.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402
from backend.src.content_flags import detect_flags  # noqa: E402
from backend.src.parser import load_show  # noqa: E402
from backend.src.spoiler_analysis import find_secrets  # noqa: E402


def secrets_and_flags(dest: Path, episodes) -> None:
    out = dest / "show_secrets_and_flags"
    out.mkdir(exist_ok=True)
    secrets = [s.model_dump() for s in find_secrets(episodes)]
    flags = [f.model_dump() for f in detect_flags(episodes)]
    (out / "show_secrets.json").write_text(json.dumps(
        {"note": "AI/heuristic-generated list of the show's secrets, each with screenplay evidence. An editor must "
                 "verify it; it is what the tool uses to decide which promos are spoilers.",
         "count": len(secrets), "secrets": secrets}, indent=1))
    by_type: dict[str, int] = {}
    for f in flags:
        by_type[f["flag_type"]] = by_type.get(f["flag_type"], 0) + 1
    (out / "content_flags.json").write_text(json.dumps(
        {"note": "Content-review signals (not legal or platform-policy decisions). No flag does not mean safe.",
         "count": len(flags), "by_type": by_type, "flags": flags}, indent=1))


def llm_calls(dest: Path) -> int:
    rows = []
    for run in sorted(d for d in dest.iterdir() if d.is_dir() and d.name[:2].isdigit()):
        raw = run / "raw_model_outputs"
        if not raw.is_dir():
            continue
        for f in sorted(raw.glob("*.json")):
            d = json.loads(f.read_text())
            if str(d.get("provider", "")).startswith("mock"):
                continue
            rows.append({"run": run.name, "file": f.name, "episode": d.get("episode"), "provider": d.get("provider"),
                         "candidate_ids": d.get("candidate_ids"), "raw_response": d.get("raw_response")})
    if rows:
        out = dest / "all_ai_calls_unedited"
        out.mkdir(exist_ok=True)
        (out / "llm_calls.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return len(rows)


def run_log(run_dir: Path) -> None:
    trace = json.loads((run_dir / "agent_execution_trace.json").read_text())
    lines = [f"{e['at']}  {e['agent']:<24} {e['action']:<18} {e.get('tool') or '':<34} {e['status']:<12} "
             f"{(str(e['duration_ms']) + 'ms') if e.get('duration_ms') else '':>8}  {e.get('detail', '')}"
             for e in trace]
    (run_dir / "run.log").write_text("\n".join(lines) + "\n")


def baselines(run_dir: Path, episodes) -> dict:
    """Coverage of the 8 reference moments by: the tool's best promo per episode, a random 30 s clip per
    episode, and the last 30 s of each episode (one clip per episode for every method, so it's fair)."""
    ref = json.loads((ROOT / "evaluation" / "reference_moments.json").read_text())["moments"]
    eps = {e.number: e for e in episodes}
    rp = run_dir / "ranked" / "ranked_promos.json"
    rp = rp if rp.exists() else run_dir / "ranked_promos.json"
    ranked = [p for p in json.loads(rp.read_text()) if p.get("rank")]
    best: dict[int, dict] = {}
    for p in ranked:                                   # ranked best-first, so the first per episode wins
        best.setdefault(p["segments"][0]["episode"], p)
    rng = random.Random(42)

    def anchor(m):
        ep = eps.get(m["episode"])
        ev = next((e for e in ep.events if m["anchor"].lower() in e.text.lower()), None) if ep else None
        return ev.start if ev else None

    rows, totals = [], {"tool_best_per_episode": 0, "random_30s": 0, "last_30s": 0}
    rand_clip = {n: (lambda s: (s, s + 30))(rng.uniform(0, max(0.0, e.duration - 30))) for n, e in eps.items()}
    for m in ref:
        t = anchor(m)
        if t is None:
            continue
        ep = eps[m["episode"]]
        p = best.get(m["episode"])
        tool = bool(p) and any(s["episode"] == m["episode"] and s["start"] - 1 <= t <= s["end"] for s in p["segments"])
        r0, r1 = rand_clip[m["episode"]]
        rnd = r0 - 1 <= t <= r1
        last = ep.duration - 30 - 1 <= t <= ep.duration
        totals["tool_best_per_episode"] += tool
        totals["random_30s"] += rnd
        totals["last_30s"] += last
        rows.append({"id": m["id"], "episode": m["episode"], "moment": m["why"], "time": round(t, 2),
                     "tool_best_promo": tool, "random_30s_clip": rnd, "last_30s_of_episode": last})
    res = {"method": "One clip per episode for every method. A reference moment counts as covered if its anchor line "
                     "falls inside that episode's clip. Random clips use seed 42.",
           "reference_moments": len(rows), "covered": totals, "per_moment": rows}
    out = run_dir / "baselines"
    out.mkdir(exist_ok=True)
    (out / "baselines.json").write_text(json.dumps(res, indent=1))
    md = ["# Baselines: tool vs simple strategies", "", res["method"], "",
          "| Method | Reference moments covered |", "|---|---|",
          f"| Tool's best promo per episode | {totals['tool_best_per_episode']}/{len(rows)} |",
          f"| Random 30 s clip per episode | {totals['random_30s']}/{len(rows)} |",
          f"| Last 30 s of each episode | {totals['last_30s']}/{len(rows)} |", "",
          "| Moment | Ep | Tool | Random 30 s | Last 30 s |", "|---|---|---|---|---|"]
    md += [f"| {r['id']} {r['moment']} | {r['episode']} | {'✓' if r['tool_best_promo'] else '—'} | "
           f"{'✓' if r['random_30s_clip'] else '—'} | {'✓' if r['last_30s_of_episode'] else '—'} |" for r in rows]
    (out / "baselines.md").write_text("\n".join(md) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=str(Path.home() / "Downloads" / "KukuPromoAI_raw_outputs"))
    a = ap.parse_args()
    dest = Path(a.dest)
    full = next(d for d in sorted(dest.iterdir()) if d.is_dir() and d.name.startswith("01_"))
    episodes = load_show(settings.data_dir)
    secrets_and_flags(dest, episodes)
    n = llm_calls(dest)
    run_log(full)
    b = baselines(full, episodes)
    print(f"secrets+flags written · {n} LLM calls · run.log · baselines {b['covered']} of {b['reference_moments']}")
    sys.path.insert(0, str(ROOT / "scripts"))
    from export_raw_outputs import write_readme_md
    write_readme_md(dest)
    for junk in dest.rglob(".DS_Store"):
        junk.unlink()
    print("zip:", shutil.make_archive(str(dest), "zip", dest.parent, dest.name))


if __name__ == "__main__":
    main()
