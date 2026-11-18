#!/usr/bin/env python3
"""Compare judging setups on the same show: rules only vs one LLM vs an LLM panel.

    python scripts/benchmark.py                       # all setups that have keys saved in .env
    python scripts/benchmark.py --setups mock groq groq+gemini --episodes 1-10

Each setup runs the full agentic pipeline in its own temp folder + database, so the app's
current results are never touched. Setups whose API key is missing are skipped (and listed).
Writes evaluation/benchmark.md and evaluation/benchmark.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402

DEFAULT_SETUPS = ["mock", "groq", "gemini", "groq+gemini"]


def parse_eps(txt: str | None) -> list[int] | None:
    if not txt:
        return None
    out = []
    for part in txt.split(","):
        a, _, b = part.strip().partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def has_keys(providers: list[str]) -> list[str]:
    return [p for p in providers if p not in ("mock", "ollama")
            and not (os.getenv("LLM_API_KEY") or os.getenv(f"{p.upper()}_API_KEY"))]


def run_setup(name: str, providers: list[str], show: str, episodes, workdir: Path) -> dict:
    from backend.agents.orchestrator import Orchestrator
    from backend.database import Database
    cfg = Settings()
    d = workdir / name.replace("+", "_")
    cfg.output_dir, cfg.db_path, cfg.checkpoint_dir = d / "outputs", d / "run.db", d / "checkpoints"
    orch = Orchestrator(cfg, Database(cfg.db_path))
    t0 = time.time()
    st = orch.create_run(episodes, {"providers": providers, "show": show})
    st = orch.execute(st.run_id)
    secs = time.time() - t0
    m = st.metrics or {}
    ref = m.get("reference", {})
    ranked = json.loads((cfg.output_dir / "ranked_promos.json").read_text()) if (cfg.output_dir / "ranked_promos.json").exists() else []
    agree = {}
    for p in ranked:
        a = (p.get("judge") or {}).get("agreement")
        if a:
            agree[a] = agree.get(a, 0) + 1
    escalated = [t for t in st.tasks if t.status.value == "NEEDS_REVIEW"]
    return {
        "setup": name, "providers": providers, "status": st.status.value, "seconds": round(secs, 1),
        "episodes": m.get("episodes"), "candidates": m.get("candidates"), "ranked": m.get("ranked"),
        "ranked_valid": m.get("ranked_valid"), "new_viewer": m.get("new_viewer"), "retarget": m.get("retarget"),
        "llm_judged": m.get("llm_judged", 0), "needs_human_review": m.get("needs_human_review"),
        "recall_top30": ref.get("recall_top_k"), "recall_any": ref.get("recall_any_rank"),
        "ref_in_scope": sum(1 for r in ref.get("moments", []) if r.get("located")), "ref_total": len(ref.get("moments", [])),
        "escalated_ids": [t.task_id + ": " + (t.error or "no promotable moment found")[:80] for t in escalated],
        "reference_ranks": {r["id"]: r.get("best_rank") for r in ref.get("moments", [])},
        "agreement": agree, "escalated_tasks": len(escalated),
        "errors": [e.get("error", "")[:160] for e in st.errors][-5:],
        "top5": [{"rank": p["rank"], "segments": " → ".join(f"Ep{s['episode']} {s['start_ts']}–{s['end_ts']}"
                                                            for s in p["segments"]),
                  "score": p["scores"]["overall"], "hook": (p.get("hook") or {}).get("text", "")[:90]}
                 for p in ranked if p.get("rank")][:5],
    }


def to_markdown(rows: list[dict], skipped: dict, meta: dict) -> str:
    ids = sorted({k for r in rows for k in r["reference_ranks"]})
    out = [f"# Benchmark: rules vs LLM judges", "",
           f"Show `{meta['show']}` · episodes {meta['episodes'] or 'all'} · {meta['when']}", "",
           "Reference check = 8 must-have moments (evaluation/reference_moments.json, AI-drafted, editor should confirm).", "",
           "| Setup | Status | Time | Ranked (valid) | New-viewer | LLM-judged cuts | Ref moments in scope | Ref in top 30 | Ref anywhere | Human review |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        pct = lambda x: "—" if x is None else f"{x * 100:.0f}%"
        out.append(f"| {r['setup']} | {r['status']} | {r['seconds']}s | {r['ranked']} ({r['ranked_valid']}) | "
                   f"{r['new_viewer']} | {r['llm_judged']} | {r.get('ref_in_scope', '—')}/{r.get('ref_total', '—')} | {pct(r['recall_top30'])} | {pct(r['recall_any'])} | "
                   f"{r['needs_human_review']} |")
    out += ["", "## Rank of each reference moment (lower is better; — = not found)", "",
            "| Moment | " + " | ".join(r["setup"] for r in rows) + " |", "|---|" + "---|" * len(rows)]
    for i in ids:
        out.append(f"| {i} | " + " | ".join(str(r["reference_ranks"].get(i) or "—") for r in rows) + " |")
    for r in rows:
        if r["agreement"]:
            out.append(f"\n**{r['setup']} panel agreement:** " + ", ".join(f"{k} {v}" for k, v in r["agreement"].items()))
        if r["errors"]:
            out.append(f"\n**{r['setup']} errors:** " + "; ".join(r["errors"]))
    if skipped:
        out += ["", "## Skipped (no API key saved)", ""] + [f"- {k}: missing {', '.join(v)}" for k, v in skipped.items()]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setups", nargs="+", default=DEFAULT_SETUPS, help="e.g. mock groq gemini groq+gemini")
    ap.add_argument("--show", default="default")
    ap.add_argument("--episodes", default="", help="e.g. 1-10 (default: all)")
    a = ap.parse_args()
    eps = parse_eps(a.episodes)
    rows, skipped = [], {}
    with tempfile.TemporaryDirectory(prefix="kukupromo-bench-") as tmp:
        for setup in a.setups:
            provs = setup.split("+")
            missing = has_keys(provs)
            if missing:
                skipped[setup] = missing
                print(f"skip {setup}: no key for {', '.join(missing)}")
                continue
            print(f"running {setup} ...", flush=True)
            try:
                rows.append(run_setup(setup, provs, a.show, eps, Path(tmp)))
                r = rows[-1]
                print(f"  {r['status']} in {r['seconds']}s · top30 recall {r['recall_top30']} · judged {r['llm_judged']}")
            except Exception as e:
                print(f"  failed: {e}")
                rows.append({"setup": setup, "providers": provs, "status": "ERROR", "seconds": 0, "episodes": None,
                             "candidates": None, "ranked": None, "ranked_valid": None, "new_viewer": None,
                             "llm_judged": 0, "needs_human_review": None, "recall_top30": None, "recall_any": None,
                             "reference_ranks": {}, "agreement": {}, "escalated_tasks": 0, "errors": [str(e)[:200]],
                             "top5": []})
    meta = {"show": a.show, "episodes": a.episodes, "when": datetime.now().strftime("%Y-%m-%d %H:%M")}
    out = ROOT / "evaluation"
    out.mkdir(exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps({"meta": meta, "results": rows, "skipped": skipped}, indent=1))
    (out / "benchmark.md").write_text(to_markdown(rows, skipped, meta))
    print(f"\nwrote {out / 'benchmark.md'}")


if __name__ == "__main__":
    main()
