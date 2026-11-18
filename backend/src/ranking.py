"""Duplicate control, alternative-cut grouping, ranking and posting priority."""
from __future__ import annotations

from .models import AltCut, Promo, ValidationStatus

STATUS_ORDER = {ValidationStatus.VALID: 0, ValidationStatus.NEEDS_REVIEW: 1, ValidationStatus.INVALID: 2}


def overlap_ratio(a: Promo, b: Promo) -> float:
    """Shared seconds / shorter promo's duration, over same-episode segments."""
    inter = 0.0
    for x in a.segments:
        for y in b.segments:
            if x.episode == y.episode:
                inter += max(0.0, min(x.end, y.end) - max(x.start, y.start))
    return inter / max(min(a.duration, b.duration), 1e-6)


def is_duplicate(a: Promo, b: Promo, threshold: float = 0.5) -> bool:
    multi_a, multi_b = len(a.episodes) > 1, len(b.episodes) > 1
    if multi_a != multi_b:
        return False          # a cross-episode trailer may reuse a single-episode moment
    return overlap_ratio(a, b) >= threshold


def _diff(head: Promo, alt: Promo) -> str:
    notes = []
    ds = alt.segments[0].start - head.segments[0].start
    de = alt.segments[-1].end - head.segments[-1].end
    if abs(ds) > 0.05:
        notes.append(f"starts {abs(ds):.1f}s {'later (tighter opening)' if ds > 0 else 'earlier (more context)'}")
    if abs(de) > 0.05:
        notes.append(f"ends {abs(de):.1f}s {'later' if de > 0 else 'earlier'}")
    if alt.kind != head.kind:
        notes.append(f"{alt.kind.replace('_', ' ')} cut")
    notes.append(f"score {alt.scores.overall:.2f} vs {head.scores.overall:.2f}")
    return "; ".join(notes)


def rank(promos: list[Promo], max_alternatives: int = 3) -> list[Promo]:
    """Return group heads in rank order; near-identical cuts are attached as alternatives."""
    ordered = sorted(promos, key=lambda p: (STATUS_ORDER[p.validation.status], -p.scores.overall, -p.rule_score))
    heads: list[Promo] = []
    for p in ordered:
        home = next((h for h in heads if is_duplicate(h, p)), None)
        if home is None:
            p.group_id = "G" + p.promo_id[1:]
            heads.append(p)
            continue
        if len(home.alternatives) < max_alternatives and \
                all(abs(a.duration - p.duration) > 1.5 or a.segments[0].start != p.segments[0].start
                    for a in home.alternatives):
            home.alternatives.append(AltCut(promo_id=p.promo_id, segments=p.segments, duration=p.duration,
                                            overall=p.scores.overall,
                                            valid=p.validation.status == ValidationStatus.VALID,
                                            difference=_diff(home, p)))
    # rank: valid first, then needs-review; invalid get no rank
    r = 0
    for i, p in enumerate(heads):
        if p.validation.status == ValidationStatus.INVALID:
            p.rank, p.posting_priority = None, "Do not post"
            p.rank_reason = "failed hard validation: " + ", ".join(c.name for c in p.validation.checks if not c.passed)
            continue
        r += 1
        p.rank = r
        nxt = next((q for q in heads[i + 1:] if q.validation.status != ValidationStatus.INVALID), None)
        gap = f"; ahead of next by {p.scores.overall - nxt.scores.overall:.2f}" if nxt else ""
        p.rank_reason = (f"#{r}: {p.scores.overall:.2f}/5 — hook {p.scores.hook:.1f}, cliffhanger {p.scores.cliffhanger:.1f}, "
                         f"makes sense alone {p.scores.standalone:.1f}{gap}")
    _priorities(heads)
    return heads


def _priorities(heads: list[Promo]) -> None:
    nv = [p for p in heads if p.rank and p.validation.status == ValidationStatus.VALID and p.category.new_viewer]
    for i, p in enumerate(nv):
        p.posting_priority = "P1 · post first" if i < 5 else "P2 · this week" if i < 15 else "P3 · backlog"
    for p in heads:
        if not p.rank or p.posting_priority:
            continue
        if p.validation.status == ValidationStatus.NEEDS_REVIEW:
            p.posting_priority = "Hold · needs human review"
        elif p.category.retarget:
            p.posting_priority = "Retargeting only"
        else:
            p.posting_priority = "P3 · backlog"
