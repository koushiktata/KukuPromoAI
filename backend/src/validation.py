"""Deterministic validation. The LLM never certifies its own timestamps: Python does."""
from __future__ import annotations

import math

from .candidate_detection import mid_line
from .models import Check, Promo, Validation, ValidationStatus
from .parser import Episode

TOL = 0.011


def _on_boundary(t: float, points: list[float]) -> bool:
    return any(abs(t - p) <= TOL for p in points)


def validate_promo(p: Promo, eps: dict[int, Episode], *, min_s=20.0, max_s=60.0, hook_window=3.0,
                   min_soft_score=2.5) -> Validation:
    checks: list[Check] = []

    def add(name, ok, detail="", severity="hard"):
        checks.append(Check(name=name, passed=bool(ok), severity=severity, detail=detail))

    missing = [s.episode for s in p.segments if s.episode not in eps]
    add("episode_exists", not missing, f"unknown episodes {missing}" if missing else "all episodes present")
    if missing:
        return Validation(status=ValidationStatus.INVALID, checks=checks)

    bad_ts = []
    for s in p.segments:
        starts, ends = eps[s.episode].boundaries()
        if not _on_boundary(s.start, starts) or not _on_boundary(s.end, ends):
            bad_ts.append(f"Ep{s.episode} {s.start_ts}-{s.end_ts}")
    add("source_timestamps_exist", not bad_ts,
        f"not on a screenplay event boundary: {bad_ts}" if bad_ts else "every cut matches a real start/end in the script")
    order_ok = all(s.start < s.end for s in p.segments)
    add("start_before_end", order_ok, "" if order_ok else "a segment ends before it starts")
    calc = all(math.isfinite(s.start) and math.isfinite(s.end) for s in p.segments)
    total = round(sum(s.end - s.start for s in p.segments), 2)
    add("duration_calculable", calc and abs(total - p.duration) < 0.05,
        f"sum of segments = {total}s (gaps not counted)")
    add("duration_20_60s", min_s <= total <= max_s, f"{total}s")

    hook_ok = bool(p.hook) and p.hook.episode == p.segments[0].episode and \
        0 <= p.hook.time - p.segments[0].start <= hook_window + TOL
    add("hook_in_first_3s", hook_ok,
        f"hook at +{(p.hook.time - p.segments[0].start):.1f}s" if p.hook else "no hook found")
    add("hook_strength", p.scores.hook >= min_soft_score, f"hook {p.scores.hook}/5", severity="soft")
    add("ending_unresolved", p.scores.cliffhanger >= min_soft_score, f"cliffhanger {p.scores.cliffhanger}/5", severity="soft")
    add("makes_sense_alone", p.scores.standalone >= min_soft_score, f"standalone {p.scores.standalone}/5", severity="soft")
    refs = all(s.source and s.source.event_ids for s in p.segments)
    add("source_references", refs, "file + line numbers for every segment" if refs else "segment without source events")

    seq_ok = [s.order for s in p.segments] == list(range(1, len(p.segments) + 1))
    for a, b in zip(p.segments, p.segments[1:]):
        if a.episode == b.episode and b.start < a.end - TOL:
            seq_ok = False
        if b.episode < a.episode:
            seq_ok = False
    add("segment_order", seq_ok, "segments in story order, no overlap" if seq_ok else "segments overlap or run backwards")
    cuts = [s for s in p.segments if mid_line(eps[s.episode], s.end, as_start=False)
            or mid_line(eps[s.episode], s.start, as_start=True)]
    add("no_mid_line_cut", not cuts, "" if not cuts else f"{len(cuts)} segment(s) cut inside a spoken line", severity="soft")

    if any(not c.passed and c.severity == "hard" for c in checks):
        status = ValidationStatus.INVALID
    elif any(not c.passed for c in checks):
        status = ValidationStatus.NEEDS_REVIEW
    else:
        status = ValidationStatus.VALID
    return Validation(status=status, checks=checks)
