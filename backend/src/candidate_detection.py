"""Hook and cliffhanger detection on top of the NLP signals."""
from __future__ import annotations

import re

from pydantic import BaseModel

from .nlp_analysis import RESOLUTION, EpisodeAnalysis
from .parser import Episode, Event

HOOK_LABELS = {"violence": 1.3, "threat": 1.1, "betrayal": 1.3, "humiliation": 1.0, "revelation": 1.1,
               "confrontation": 1.0, "unexpected_arrival": 0.9, "power_shift": 0.9, "emotional_breakdown": 0.6,
               "turn": 0.6, "revenge": 0.8}
CLIFF_LABELS = {"suspense": 1.1, "unanswered_question": 1.2, "threat": 1.1, "unexpected_arrival": 1.2,
                "revelation": 1.0, "violence": 0.8, "confrontation": 0.6, "power_shift": 0.7, "turn": 0.6}
BACKREF = re.compile(r"\b(again|remember|still|after what|you promised|last night|earlier|as i said|once more)\b", re.I)


class MomentScore(BaseModel):
    time: float
    strength: float
    event_id: str
    text: str
    kind: str
    labels: dict[str, float]


def _event_hook_value(ev: Event, an: EpisodeAnalysis) -> float:
    sig = an.signals[ev.event_id]
    v = sum(HOOK_LABELS.get(k, 0) * c for k, c in sig.labels.items())
    v += sig.arousal * (1.0 if ev.kind in ("DIALOGUE", "ACTION") else 0.5)
    if sig.punchy:
        v += 0.6
    if ev.kind == "CAMERA":
        v *= 0.6        # camera notes describe visuals; useful but weaker evidence than action/dialogue
    return v


def _event_cliff_value(ev: Event, an: EpisodeAnalysis) -> float:
    sig = an.signals[ev.event_id]
    v = sum(CLIFF_LABELS.get(k, 0) * c for k, c in sig.labels.items()) + 0.5 * sig.arousal
    if RESOLUTION.search(ev.text) and not sig.labels.get("suspense"):
        v -= 1.0        # warm / resolved beat is the opposite of a cliffhanger
    if ev.kind == "CAMERA":
        v *= 0.7
    return v


def mid_line(ep: Episode, t: float, *, as_start: bool) -> bool:
    """True if cutting at t would split a spoken line."""
    for e in ep.events:
        if e.kind != "DIALOGUE":
            continue
        if as_start and e.start + 0.05 < t < e.end - 0.2:
            return True
        if not as_start and e.start + 0.2 < t < e.end - 0.2:
            return True
    return False


def hook_at(ep: Episode, an: EpisodeAnalysis, start: float, window: float = 3.0) -> MomentScore | None:
    evs = [e for e in ep.events if start - 1e-6 <= e.start < start + window]
    if not evs:
        return None
    best = max(evs, key=lambda e: _event_hook_value(e, an))
    return MomentScore(time=best.start, strength=round(_event_hook_value(best, an), 3), event_id=best.event_id,
                       text=best.text, kind=best.kind, labels=an.signals[best.event_id].labels)


def cliff_at(ep: Episode, an: EpisodeAnalysis, end: float, window: float = 4.0) -> MomentScore | None:
    evs = [e for e in ep.events if end - window <= e.end <= end + 1e-6 and e.start < end]
    if not evs:
        return None
    best = max(evs, key=lambda e: _event_cliff_value(e, an))
    v = _event_cliff_value(best, an)
    if ep.duration - end < 2.5:
        v += 1.0        # writers end episodes on cliffhangers (moderate bonus; was over-weighted in v1)
    # cutting right before a high-intensity payoff is itself a cliffhanger
    nxt = [e for e in ep.events if end <= e.start < end + 4 and e.kind in ("DIALOGUE", "ACTION")]
    if nxt and max(an.signals[e.event_id].arousal for e in nxt) >= 0.85:
        v += 0.6
    return MomentScore(time=best.start, strength=round(v, 3), event_id=best.event_id, text=best.text,
                       kind=best.kind, labels=an.signals[best.event_id].labels)


def hook_candidates(ep: Episode, an: EpisodeAnalysis, top: int = 8) -> list[MomentScore]:
    starts = sorted({0.0} | {e.start for e in ep.events})
    out = []
    for s in starts:
        if mid_line(ep, s, as_start=True) or ep.duration - s < 8:
            continue
        h = hook_at(ep, an, s)
        if h and h.strength > 0.8:
            out.append(h.model_copy(update={"time": s}))
    out.sort(key=lambda m: -m.strength)
    keep: list[MomentScore] = []
    for m in out:                     # spread out: at least 6s apart
        if all(abs(m.time - k.time) > 6 for k in keep):
            keep.append(m)
        if len(keep) >= top:
            break
    return keep


def cliff_candidates(ep: Episode, an: EpisodeAnalysis, top: int = 8) -> list[MomentScore]:
    ends = sorted({e.end for e in ep.events if e.kind != "CAMERA"} | {ep.duration})
    out = []
    for t in ends:
        if mid_line(ep, t, as_start=False) or t < 8:
            continue
        c = cliff_at(ep, an, t)
        if c and c.strength > 0.6:
            out.append(c.model_copy(update={"time": t}))
    out.sort(key=lambda m: -m.strength)
    keep: list[MomentScore] = []
    for m in out:
        if all(abs(m.time - k.time) > 5 for k in keep):
            keep.append(m)
        if len(keep) >= top:
            break
    return keep
