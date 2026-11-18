"""Exports (CSV / JSON / Markdown). Built from stored promo dicts + editor decisions."""
from __future__ import annotations

import csv
import io

DECISION_LABEL = {"approved": "Approved", "rejected": "Rejected", "not_reviewed": "Not reviewed"}


def seg_str(p: dict) -> str:
    return " → ".join(f"Ep{s['episode']} {s['start_ts']}–{s['end_ts']}" for s in p["segments"])


def flat_row(p: dict) -> dict:
    sc, rv = p["scores"], p.get("review", {})
    return {
        "rank": p.get("rank") or "", "promo_id": p["promo_id"], "posting_priority": p.get("posting_priority", ""),
        "kind": p["kind"], "episodes": "→".join(str(e) for e in sorted({s["episode"] for s in p["segments"]})),
        "segments": seg_str(p), "duration_s": p["duration"],
        "hook_ts": f"Ep{p['hook']['episode']} {p['hook']['ts']}" if p.get("hook") else "",
        "hook": p["hook"]["text"] if p.get("hook") else "",
        "cliffhanger_ts": f"Ep{p['cliffhanger']['episode']} {p['cliffhanger']['ts']}" if p.get("cliffhanger") else "",
        "cliffhanger": p["cliffhanger"]["text"] if p.get("cliffhanger") else "",
        "why_it_works": p.get("why_it_works", ""),
        "overall": sc["overall"], "hook_score": sc["hook"], "cliffhanger_score": sc["cliffhanger"],
        "standalone_score": sc["standalone"], "emotion_score": sc["emotion"], "coherence_score": sc["coherence"],
        "score_source": sc["source"], "validation": p["validation"]["status"],
        "new_viewer": p["category"]["new_viewer"], "retarget_spoiler": p["category"]["retarget"],
        "category_reason": p["category"]["explanation"],
        "judge": f"{p['judge']['verdict']} — {p['judge']['comment']}".strip(" —"),
        "content_flags": len(p.get("content_flag_ids", [])), "needs_human_review": p.get("needs_human_review", False),
        "editor_decision": DECISION_LABEL.get(rv.get("decision", "not_reviewed"), "Not reviewed"),
        "editor_reason": rv.get("reason", ""), "reviewed_at": rv.get("updated_at", ""),
    }


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    if not rows:
        buf.write("rank,promo_id,segments,editor_decision\n")
        return buf.getvalue()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def markdown_report(promos: list[dict], secrets: list[dict], flags: list[dict], stats: dict, run: dict | None,
                    show: str = "") -> str:
    flag_by_id = {f["flag_id"]: f for f in flags}
    m = (run or {}).get("metrics", {})
    rate = "—" if stats["approval_rate"] is None else f"{stats['approval_rate'] * 100:.0f}%"
    out = [f"# KukuPromo AI — ranked promos{(' · ' + show) if show else ''}", "",
           f"Run `{(run or {}).get('run_id', '-')}` · provider `{m.get('provider', '-')}` · "
           f"{m.get('episodes', '?')} episodes · {m.get('candidates', '?')} candidates · {m.get('ranked', '?')} ranked", "",
           "> **Before posting:** review potential graphic/sexual content flags and check the show's secrets list. "
           "Spoiler labels are AI-generated and must be verified.", "",
           f"**Editor review:** {stats['reviewed']} / {stats['total']} reviewed · {stats['approved']} approved · "
           f"{stats['rejected']} rejected · approval rate {rate}", "",
           "Scoring weights are our own assumption (hook 25%, cliffhanger 30%, standalone 20%, emotion 15%, "
           "coherence 10%), not official Kuku criteria.", ""]
    for p in promos:
        if not p.get("rank"):
            continue
        sc = p["scores"]
        rv = p.get("review", {})
        cats = [c for c, on in (("For new viewers", p["category"]["new_viewer"]),
                                ("Re-targeting / spoilers", p["category"]["retarget"])) if on] or ["No audience fit"]
        out += [f"## #{p['rank']} · Ep {' → '.join(str(e) for e in sorted({s['episode'] for s in p['segments']}))} · "
                f"{p['duration']:.0f}s · score {sc['overall']:.2f} · {p.get('posting_priority', '')}", "",
                f"- **Segments (in order):** {seg_str(p)}",
                f"- **Hook (Ep{p['hook']['episode']} {p['hook']['ts']}):** {p['hook']['text']}" if p.get("hook") else "- Hook: —",
                f"- **Cliffhanger (Ep{p['cliffhanger']['episode']} {p['cliffhanger']['ts']}):** {p['cliffhanger']['text']}" if p.get("cliffhanger") else "- Cliffhanger: —",
                f"- **Why it works:** {p.get('why_it_works', '')}",
                f"- **Why this rank:** {p.get('rank_reason', '')}",
                f"- **Scores:** {sc['explanation']}",
                f"- **Judge:** {p['judge']['verdict']} — {p['judge']['comment']} ({p['judge']['provider']})",
                f"- **Validation:** {p['validation']['status']}"
                + "".join(f" · ✗ {c['name']} ({c['detail']})" for c in p["validation"]["checks"] if not c["passed"]),
                f"- **Audience:** {', '.join(cats)} — {p['category']['explanation']}"]
        fl = [flag_by_id[f] for f in p.get("content_flag_ids", []) if f in flag_by_id]
        if fl:
            out.append("- **Content flags:** " + "; ".join(f"{f['flag_type']} ({f['severity']}, Ep{f['episode']} {f['ts']})" for f in fl))
        for a in p.get("alternatives", [])[:3]:
            out.append(f"- **Alternative cut:** {seg_str(a)} "
                       f"· {a['duration']:.0f}s · score {a['overall']:.2f} · {a['difference']}")
        if p.get("quality_notes"):
            out.append("- **Quality notes:** " + "; ".join(p["quality_notes"]))
        out += [f"- **Editor decision:** {DECISION_LABEL.get(rv.get('decision', 'not_reviewed'))}"
                + (f" — {rv['reason']}" if rv.get("reason") else ""), ""]
    out += ["## The show's secrets (AI-generated — verify before relying on them)", ""]
    for s in secrets:
        out.append(f"- **{s['theme']}** (Ep {s['reveal_episode']}, {s['severity']}, confidence {s['confidence']}, "
                   f"review: {s.get('review', {}).get('status', 'unreviewed')}): {s['description']}")
    inval = [p for p in promos if not p.get("rank")]
    if inval:
        out += ["", "## Rejected by validation", ""]
        out += [f"- {seg_str(p)} — {p.get('rank_reason', '')}" for p in inval]
    return "\n".join(out) + "\n"
