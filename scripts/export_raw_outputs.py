#!/usr/bin/env python3
"""Produce the 'Raw outputs' folder for submission: fresh, unedited runs on the full input pack.

    python scripts/export_raw_outputs.py                      # rules-only on all 50 + Groq judge on episodes 1-10
    python scripts/export_raw_outputs.py --groq-episodes 1-50  # Groq on the full show (slow on the free tier)
    python scripts/export_raw_outputs.py --no-groq

Writes ~/Downloads/KukuPromoAI_raw_outputs/ and ~/Downloads/KukuPromoAI_raw_outputs.zip.
Runs use their own folders + databases, so the app's data is never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402

SKIP = {"checkpoints", "kukupromo.db", "run.db", "run.db-wal", "run.db-shm"}


def parse_eps(txt: str):
    if not txt:
        return None
    out = []
    for part in txt.split(","):
        a, _, b = part.strip().partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def run(name: str, providers: list[str], episodes, work: Path, dest: Path) -> dict:
    from backend.agents.orchestrator import Orchestrator
    from backend.database import Database
    cfg = Settings()
    d = work / name
    cfg.output_dir, cfg.db_path, cfg.checkpoint_dir = d / "outputs", d / "run.db", d / "checkpoints"
    orch = Orchestrator(cfg, Database(cfg.db_path))
    t0 = time.time()
    st = orch.execute(orch.create_run(episodes, {"providers": providers}).run_id)
    target = dest / name
    target.mkdir(parents=True, exist_ok=True)
    for p in cfg.output_dir.iterdir():
        if p.name in SKIP:
            continue
        if p.is_dir():
            if p.name == "raw_model_outputs" and providers != ["mock"]:   # real LLM replies only
                runs = [x for x in p.iterdir() if x.is_dir()]
                if runs and any(runs[0].iterdir()):
                    shutil.copytree(runs[0], target / "raw_model_outputs")
            continue
        shutil.copy2(p, target / p.name)
    m = st.metrics or {}
    return {"name": name, "status": st.status.value, "seconds": round(time.time() - t0, 1),
            "episodes": m.get("episodes"), "ranked": m.get("ranked"), "llm_judged": m.get("llm_judged", 0),
            "provider": m.get("provider"), "errors": [e.get("error", "")[:150] for e in st.errors][-3:]}


README = """KukuPromo AI — raw outputs (unedited)
Generated {when} by scripts/export_raw_outputs.py on the full input pack ({episodes} episodes).

{runs}

What each file is (inside each run folder)
- ranked.md                 Ranked promos: every segment's episode + start–end in order, hook, cliffhanger,
                            why it works, why this rank, validation, audience, alternative cuts.
- ranked_promos.csv / .json Same promos as a table / full detail (scores, checks, flags, alternatives).
- candidate_moments.json    Every candidate cut the tool generated (before de-duplication / ranking).
- validated_promos.json     The 12 deterministic validation checks for every candidate.
- evaluation_results.csv    Per-promo check results + scores.
- evaluation_summary.json   Run-level metrics + the 8-moment reference check.
- agent_execution_trace.json / agent_run_summary.json   Orchestrator + agent + tool-call trace.
- processing_report.json, data_inventory.json, screenplay_format_report.md   Input inventory and parser report.
- parsed_screenplays.json   The parser's structured output (every timed event with its source line number).
- raw_model_outputs/        (LLM runs only) the model's unedited JSON reply for every judged episode.

Also included
- benchmark/                Rules vs LLM judge comparison (evaluation/benchmark.md / .json).
- reference_moments.json    The 8 must-have moments used for the reference check.

Note: these files quote Kuku's screenplays; they are shared only for this assignment.
"""


FILES = [
    ("ranked/ranked.md", "**Start here.** Ranked promos: every segment's episode and start–end time in order, the hook "
                         "and cliffhanger with timestamps, why it works, why this rank, judge comment, validation, "
                         "audience, content flags and alternative cuts."),
    ("ranked/ranked_promos.csv", "The same ranked promos as a spreadsheet (opens in Google Sheets)."),
    ("ranked/ranked_promos.json", "Full detail for every ranked promo (all scores, checks, flags, alternatives)."),
    ("ranked/evaluation_results.csv", "One row per ranked promo: each check passed/failed and each score."),
    ("candidates/ep01.json …", "Every candidate cut found in that episode, with its scores and validation result."),
    ("candidates/candidate_moments.json", "All candidates in one file, before de-duplication and ranking."),
    ("candidates/validated_promos.json", "The 12 deterministic validation checks for every candidate."),
    ("cross_episode/ep01-02.json …", "Trailer-style candidates joining two neighbouring episodes."),
    ("parsed/events.csv", "Every timed line of every episode (camera / action / sound / dialogue) with its source line."),
    ("parsed/episodes.json", "Per-episode summary: duration, logline, scenes, events."),
    ("parsed/parsed_screenplays.json", "The parser's full structured output."),
    ("parsed/data_inventory.json, screenplay_format_report.md", "Input inventory and how the format was read."),
    ("evaluation_summary.json", "Run-level metrics and the 8-moment reference check."),
    ("agent_run_summary.json", "Per-agent task counts, retries and errors for the run."),
    ("agent_execution_trace.json", "Every orchestrator, agent and tool-call step with timing and status."),
    ("run.log", "The same trace as a readable, line-by-line log (full-show run)."),
    ("processing_report.json", "What was processed: files found, episodes, parser issues, provider."),
    ("baselines/", "Full-show run: the tool vs a random 30 s clip and the last 30 s of each episode."),
    ("raw_model_outputs/", "LLM runs only: the model's unedited JSON reply for each judged episode."),
]


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def write_readme_md(dest: Path) -> Path:
    """README.md for the raw-outputs folder, in plain Markdown so Google Docs can open it."""
    runs = [d for d in sorted(dest.iterdir()) if d.is_dir() and d.name[:2].isdigit()]
    out = ["# KukuPromo AI — raw outputs", "",
           "Unedited outputs from running KukuPromo AI (Kuku AI Generalist assignment, **Problem 1: Find the Promos**) "
           "on the full input pack. Nothing in these files was edited by hand.", "",
           f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}", "",
           "## What's in this folder", "",
           "| Folder / file | What it is |", "|---|---|"]
    summaries = {}
    for d in runs:
        s = _load(d / "evaluation_summary.json", {}) or {}
        pr = _load(d / "processing_report.json", {}) or {}
        summaries[d.name] = (s, pr)
        judge = "rules only (no LLM)" if s.get("provider", "").startswith("mock") else f"LLM judge: {s.get('provider')}"
        out.append(f"| `{d.name}/` | {s.get('episodes', '?')} episodes · {judge} · {s.get('ranked', '?')} ranked promos "
                   f"({s.get('ranked_valid', '?')} fully valid) · {s.get('llm_judged', 0)} cuts judged by the LLM |")
    if (dest / "benchmark").is_dir():
        out.append("| `benchmark/` | Rules vs LLM judge comparison: where each must-have moment ranks under each setup |")
    if (dest / "reference_moments.json").exists():
        out.append("| `reference_moments.json` | The 8 must-have moments used for the reference check |")
    if (dest / "evaluation").is_dir():
        out.append("| `evaluation/` | `benchmark.md` / `.json` (rules vs LLM judge: where each must-have moment ranks), "
                   "`reference_moments.json` (the 8 must-have moments), `runs.json` (what was run, how long, errors) |")
    if (dest / "all_ai_calls_unedited").is_dir():
        calls = next(iter(sorted((dest / "all_ai_calls_unedited").glob("llm_calls*"))), None)
        out.append(f"| `all_ai_calls_unedited/{calls.name if calls else 'llm_calls.jsonl'}` | Every LLM judge reply in "
                   "one file, one JSON object per line (one line per call), unedited |")
    if (dest / "show_secrets_and_flags").is_dir():
        out.append("| `show_secrets_and_flags/` | The show's secrets the tool treats as spoilers (with screenplay "
                   "evidence) and the content flags (violence, threats…) — both need an editor's check |")
    full = next((d for d in runs if (d / "baselines" / "baselines.json").exists()), None)
    base = _load(full / "baselines" / "baselines.json", {}) if full else {}
    out += ["", "## Results at a glance", ""]
    if base:
        c, n = base["covered"], base["reference_moments"]
        out += ["**Baselines (one clip per episode for every method, 8 must-have moments):** the tool's best promo "
                f"covers {c['tool_best_per_episode']}/{n}, a random 30 s clip {c['random_30s']}/{n}, and the last 30 s of "
                f"each episode {c['last_30s']}/{n}. Details: `{full.name}/baselines/`.", ""]
    for name, (s, pr) in summaries.items():
        ref = s.get("reference") or {}
        out += [f"### {name}", "",
                f"- **Episodes processed:** {s.get('episodes', '?')} of {pr.get('files_found', '?')} files found "
                f"(missing: {pr.get('missing_episodes') or 'none'})",
                f"- **Candidates:** {s.get('candidates', '?')} cuts generated → {s.get('candidates_valid', '?')} passed "
                f"every rule → **{s.get('ranked', '?')} distinct promos** ranked, with {s.get('alternative_cuts', '?')} "
                f"alternative cuts",
                f"- **Audience:** {s.get('new_viewer', '?')} for new viewers, {s.get('retarget', '?')} for re-targeting",
                f"- **Hook within the first 3 seconds:** {round((s.get('hook_within_3s_rate') or 0) * 100)}% of ranked promos "
                f"· average length {s.get('mean_duration_s', '?')} s",
                f"- **Judge:** {'rules only (offline, no LLM)' if str(s.get('provider', '')).startswith('mock') else s.get('provider', '?')}"
                f" · {s.get('llm_judged', 0)} cuts judged by the LLM",
                f"- **Processing time:** {s.get('processing_seconds', '?')} s"]
        if ref.get("available"):
            located = [m for m in ref.get("moments", []) if m.get("located")]
            out.append(f"- **Reference check:** {len(located)} of {len(ref.get('moments', []))} must-have moments are in "
                       f"these episodes; {sum(1 for m in located if m.get('hit_any'))} appear in the ranking, "
                       f"{sum(1 for m in located if m.get('hit_top_k'))} in the top {ref.get('top_k')}")
        top = (_load(dest / name / "ranked" / "ranked_promos.json")
               or _load(dest / name / "ranked_promos.json", []) or [])[:5]
        if top:
            out += ["", "**Top 5 promos (exact cuts):**", "",
                    "| Rank | Cut these timestamps (in order) | Length | Hook (first 3 s) | Score |", "|---|---|---|---|---|"]
            for p in top:
                if not p.get("rank"):
                    continue
                segs = " → ".join(f"Ep{x['episode']} {x['start_ts']}–{x['end_ts']}" for x in p["segments"])
                hook = ((p.get("hook") or {}).get("text") or "").replace("|", "/")
                hook = hook if len(hook) <= 80 else hook[:77].rsplit(" ", 1)[0] + "…"
                out.append(f"| {p['rank']} | {segs} | {round(p['duration'])} s | {hook} | {p['scores']['overall']:.2f} |")
        out.append("")
    out += ["## What each file is (inside each run folder)", "", "| File | What it is |", "|---|---|"]
    out += [f"| `{f}` | {d} |" for f, d in FILES]
    out += ["", "## How to read a promo", "",
            "Each promo in `ranked/ranked.md` lists its **segments in order**, for example `Ep3 00:58.20–01:33.60`. Cut "
            "exactly these timestamps from those episodes and join them in the order given. Timestamps are relative to "
            "each episode (every episode starts at 00:00) and always land on a real line or shot in the screenplay.", "",
            "## Notes", "",
            "- Scoring weights (hook 25%, cliffhanger 30%, standalone 20%, emotion 15%, coherence 10%) are my own "
            "assumption, not Kuku's criteria.",
            "- Spoiler labels and the show's secrets list are AI-generated and should be checked by an editor.",
            "- LLM runs on the free tier hit rate limits; the tool waits and retries automatically (visible in "
            "`agent_execution_trace.json`). LLM answers vary slightly between runs.",
            "- These files quote Kuku's screenplays and are shared only for this assignment.", ""]
    path = dest / "README.md"
    path.write_text("\n".join(out))
    old = dest / "README.txt"
    if old.exists():
        old.unlink()
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groq-episodes", default="1-10")
    ap.add_argument("--no-groq", action="store_true")
    ap.add_argument("--readme-only", action="store_true", help="only (re)write README.md in an existing export + re-zip")
    ap.add_argument("--dest", default=str(Path.home() / "Downloads" / "KukuPromoAI_raw_outputs"))
    a = ap.parse_args()
    dest = Path(a.dest)
    if a.readme_only:
        p = write_readme_md(dest)
        for junk in dest.rglob(".DS_Store"):
            junk.unlink()
        zip_path = shutil.make_archive(str(dest), "zip", dest.parent, dest.name)
        print(f"wrote {p}\nzip:  {zip_path}")
        return
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    work = dest.parent / (dest.name + "_work")
    if work.exists():
        shutil.rmtree(work)
    results = []
    try:
        print("1/2 rules only, all episodes ...", flush=True)
        results.append(run("01_full_show_rules_only", ["mock"], None, work, dest))
        print("   ", results[-1], flush=True)
        if not a.no_groq:
            if not (os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")):
                print("2/2 skipped: no Groq key saved", flush=True)
            else:
                eps = parse_eps(a.groq_episodes)
                name = f"02_episodes_{a.groq_episodes.replace(',', '_')}_groq_judge"
                print(f"2/2 Groq judge, episodes {a.groq_episodes} (a few minutes on the free tier) ...", flush=True)
                results.append(run(name, ["groq"], eps, work, dest))
                print("   ", results[-1], flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    bench = dest / "benchmark"
    bench.mkdir()
    for f in ("benchmark.md", "benchmark.json"):
        if (ROOT / "evaluation" / f).exists():
            shutil.copy2(ROOT / "evaluation" / f, bench / f)
    shutil.copy2(ROOT / "evaluation" / "reference_moments.json", dest / "reference_moments.json")
    lines = "\n".join(f"- {r['name']}: {r['status']}, {r['episodes']} episodes, {r['ranked']} ranked promos, "
                      f"{r['llm_judged']} cuts judged by LLM ({r['provider']}), {r['seconds']} s"
                      + (f", errors: {r['errors']}" if r["errors"] else "") for r in results)
    (dest / "runs.json").write_text(json.dumps(results, indent=1))
    write_readme_md(dest)
    zip_path = shutil.make_archive(str(dest), "zip", dest.parent, dest.name)
    print(f"\nfolder: {dest}\nzip:    {zip_path}")


if __name__ == "__main__":
    main()
