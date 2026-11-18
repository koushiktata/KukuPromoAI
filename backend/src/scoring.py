"""Explainable 1-5 scoring. Weights are our own assumption, not official Kuku criteria."""
from __future__ import annotations

import re

from .candidate_detection import BACKREF
from .character_analysis import canonical
from .models import Promo, Scores
from .nlp_analysis import RESOLUTION, EpisodeAnalysis
from .parser import Episode

CRITERIA = ("hook", "cliffhanger", "standalone", "emotion", "coherence")
LABELS = {"hook": "Hook", "cliffhanger": "Cliffhanger", "standalone": "Makes sense alone",
          "emotion": "Emotional intensity", "coherence": "Narrative coherence"}


def clamp(x: float, lo: float = 1.0, hi: float = 5.0) -> float:
    return round(max(lo, min(hi, x)), 2)


def _events(p: Promo, eps: dict[int, Episode]):
    for s in p.segments:
        for e in eps[s.episode].events:
            if s.start - 1e-6 <= e.start < s.end - 1e-6:
                yield e


class Calibrator:
    """Maps raw rule strengths to 1-5 by percentile within this show's candidate pool, so scores
    spread across the scale instead of saturating. Falls back to a fixed mapping when empty."""

    def __init__(self, hooks: list[float] | None = None, cliffs: list[float] | None = None):
        self.hooks, self.cliffs = sorted(hooks or []), sorted(cliffs or [])

    @staticmethod
    def _pct(sorted_vals: list[float], x: float) -> float:
        import bisect
        return bisect.bisect_right(sorted_vals, x) / len(sorted_vals)

    def hook(self, raw: float) -> float:
        return clamp(1 + 4 * self._pct(self.hooks, raw)) if self.hooks else clamp(1 + (raw - 0.8) / 0.6)

    def cliff(self, raw: float) -> float:
        return clamp(1 + 4 * self._pct(self.cliffs, raw)) if self.cliffs else clamp(1 + raw * 1.4)

    def to_dict(self) -> dict:
        return {"hooks": self.hooks, "cliffs": self.cliffs}


def heuristic_scores(p: Promo, eps: dict[int, Episode], ans: dict[int, EpisodeAnalysis],
                     cal: Calibrator | None = None) -> dict[str, float]:
    cal = cal or Calibrator()
    evs = list(_events(p, eps))
    hook = cal.hook(p.rule_hook)
    cliff = cal.cliff(p.rule_cliff)
    if p.cliffhanger and RESOLUTION.search(p.cliffhanger.text) and not p.cliffhanger.labels.get("suspense"):
        cliff = clamp(cliff - 1)
    spoken = [ans[e.episode].signals[e.event_id].arousal for e in evs if e.kind in ("DIALOGUE", "ACTION")]
    emotion = clamp(1 + 4 * (sum(spoken) / max(len(spoken), 1)) ** 1.3) if spoken else 1.0
    # standalone: does a stranger get who/what/stakes?
    speakers = {canonical(e.speaker) for e in evs if e.kind == "DIALOGUE"}
    text = " ".join(e.text for e in evs if e.kind in ("DIALOGUE", "ACTION"))
    standalone = 4.5
    standalone -= 0.4 * max(0, len(speakers) - 3)
    standalone -= 0.6 * min(2, len(BACKREF.findall(text)))
    first = p.segments[0].episode
    standalone -= 0.5 if first > 20 else 0
    standalone -= 0.5 if first > 38 else 0
    if any(k in p.labels for k in ("betrayal", "humiliation", "threat", "violence", "confrontation")):
        standalone += 0.5          # visible conflict: who is wronged is obvious
    if len(re.findall(r"\b(he|she|they|him|her|them)\b", (p.hook.text if p.hook else "").lower())) >= 2 and not speakers:
        standalone -= 0.5
    if p.kind == "cross_episode":
        standalone -= 0.3
    # coherence
    scenes = {(s.episode, e.scene_id) for s in p.segments for e in eps[s.episode].events
              if s.start - 1e-6 <= e.start < s.end - 1e-6}
    if p.kind == "continuous":
        coherence = 5.0 if len(scenes) <= 1 else 4.3
    elif p.kind == "multi_segment":
        coherence = 4.0 if len(scenes) <= 1 else 3.5
    else:
        a, b = p.segments[0].episode, p.segments[-1].episode
        seg_speakers = [{canonical(e.speaker) for e in eps[s.episode].events
                         if e.kind == "DIALOGUE" and s.start <= e.start < s.end} for s in p.segments]
        shared = bool(seg_speakers[0] & seg_speakers[-1])
        coherence = 3.0 + (0.5 if b - a == 1 else 0) + (0.5 if shared else 0)
    return {"hook": hook, "cliffhanger": cliff, "standalone": clamp(standalone), "emotion": emotion,
            "coherence": clamp(coherence)}


def weighted(scores: dict[str, float], weights: dict[str, float]) -> float:
    tot = sum(weights.values()) or 1
    return round(sum(scores[k] * weights[k] for k in CRITERIA) / tot, 2)


def apply_scores(p: Promo, heur: dict[str, float], weights: dict[str, float],
                 llm: dict[str, float] | None = None, llm_name: str = "") -> Promo:
    final = dict(heur)
    source = "heuristic"
    if llm:
        for k in CRITERIA:
            if k in llm and isinstance(llm[k], (int, float)):
                final[k] = clamp(0.6 * float(llm[k]) + 0.4 * heur[k])
        source = f"blended (60% {llm_name}, 40% rules)"
    overall = weighted(final, weights)
    expl = " · ".join(f"{LABELS[k]} {final[k]:.1f}/5" for k in CRITERIA)
    wtxt = ", ".join(f"{k} {int(round(w * 100))}%" for k, w in weights.items())
    p.scores = Scores(**final, overall=overall, source=source,
                      explanation=f"{expl} → {overall:.2f}/5 (weights, our assumption: {wtxt})")
    return p
