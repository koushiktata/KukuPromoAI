"""Evaluation: per-promo check table + run-level metrics + recall on a small reference set."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Promo, ValidationStatus
from .parser import Episode

REFERENCE = Path(__file__).resolve().parents[2] / "evaluation" / "reference_moments.json"


def promo_rows(ranked: list[Promo]) -> list[dict]:
    rows = []
    for p in ranked:
        checks = {c.name: c.passed for c in p.validation.checks}
        rows.append({
            "promo_id": p.promo_id, "rank": p.rank or "", "kind": p.kind,
            "episodes": "→".join(map(str, p.episodes)), "duration_s": p.duration,
            "status": p.validation.status.value, **{f"check_{k}": v for k, v in checks.items()},
            "hook": p.scores.hook, "cliffhanger": p.scores.cliffhanger, "standalone": p.scores.standalone,
            "emotion": p.scores.emotion, "coherence": p.scores.coherence, "overall": p.scores.overall,
            "score_source": p.scores.source, "new_viewer": p.category.new_viewer, "retarget": p.category.retarget,
            "spoilers": len(p.category.spoiler_secret_ids), "content_flags": len(p.content_flag_ids),
            "judge_verdict": p.judge.verdict, "needs_human_review": p.needs_human_review,
            "alternatives": len(p.alternatives), "quality_notes": "; ".join(p.quality_notes),
        })
    return rows


def reference_recall(ranked: list[Promo], episodes: dict[int, Episode], top_k: int = 30) -> dict:
    if not REFERENCE.exists():
        return {"available": False}
    ref = json.loads(REFERENCE.read_text())["moments"]
    pool = [p for p in ranked if p.rank and p.rank <= top_k] if top_k else [p for p in ranked if p.rank]
    all_ranked = [p for p in ranked if p.rank]
    results = []
    for m in ref:
        ep = episodes.get(m["episode"])
        ev = next((e for e in ep.events if m["anchor"].lower() in e.text.lower()), None) if ep else None
        if not ev:
            results.append({**m, "located": False, "hit_top_k": False, "hit_any": False})
            continue

        def covers(p: Promo) -> bool:
            return any(s.episode == m["episode"] and s.start - 1 <= ev.start <= s.end for s in p.segments)
        hit_k = next((p.rank for p in pool if covers(p)), None)
        hit_any = next((p.rank for p in all_ranked if covers(p)), None)
        results.append({**m, "located": True, "time": round(ev.start, 2), "hit_top_k": hit_k is not None,
                        "best_rank": hit_any, "hit_any": hit_any is not None})
    located = [r for r in results if r["located"]]
    return {"available": True, "top_k": top_k, "moments": results,
            "recall_top_k": round(sum(r["hit_top_k"] for r in located) / max(len(located), 1), 3),
            "recall_any_rank": round(sum(r["hit_any"] for r in located) / max(len(located), 1), 3)}


def summary(candidates: list[Promo], ranked: list[Promo], episodes: dict[int, Episode], secrets, flags,
            seconds: float, provider: str) -> dict:
    st = [p.validation.status for p in candidates]
    rk = [p for p in ranked if p.rank]
    valid_r = [p for p in rk if p.validation.status == ValidationStatus.VALID]
    covered = {s.episode for p in valid_r for s in p.segments}
    return {
        "provider": provider,
        "episodes": len(episodes),
        "candidates": len(candidates),
        "candidates_valid": st.count(ValidationStatus.VALID),
        "candidates_needs_review": st.count(ValidationStatus.NEEDS_REVIEW),
        "candidates_invalid": st.count(ValidationStatus.INVALID),
        "distinct_moments": len(ranked),
        "ranked": len(rk),
        "ranked_valid": len(valid_r),
        "alternative_cuts": sum(len(p.alternatives) for p in ranked),
        "new_viewer": sum(p.category.new_viewer for p in rk),
        "retarget": sum(p.category.retarget for p in rk),
        "llm_judged": sum(1 for p in candidates if "blended" in p.scores.source),
        "mean_duration_s": round(sum(p.duration for p in rk) / max(len(rk), 1), 1),
        "hook_within_3s_rate": round(sum(1 for p in rk if any(c.name == "hook_in_first_3s" and c.passed
                                                           for c in p.validation.checks)) / max(len(rk), 1), 3),
        "episode_coverage": f"{len(covered)}/{len(episodes)}",
        "needs_human_review": sum(p.needs_human_review for p in rk),
        "secrets": len(secrets), "content_flags": len(flags),
        "processing_seconds": round(seconds, 1),
        "reference": reference_recall(ranked, episodes),
    }
