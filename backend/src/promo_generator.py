"""Generate promo candidates. Every cut point is a real event boundary from the screenplay.

Three shapes:
  continuous     one stretch, 20-60s
  multi_segment  hook stretch + cliffhanger stretch from the same episode (skips the slow middle)
  cross_episode  hook from episode N + cliffhanger from N+1 / N+2 (a mini trailer)
Overlapping variants are deliberately kept: ranking groups them as alternative cuts.
"""
from __future__ import annotations

from .candidate_detection import cliff_at, cliff_candidates, hook_at, hook_candidates, mid_line
from .models import Moment, Promo, Segment, SourceRef, promo_id_for
from .nlp_analysis import EpisodeAnalysis
from .parser import Episode, fmt_ts

MIN_S, MAX_S, SWEET = 20.0, 60.0, (28.0, 45.0)


def make_segment(ep: Episode, start: float, end: float, order: int, reason: str) -> Segment:
    evs = [e for e in ep.events if start - 1e-6 <= e.start < end - 1e-6]
    src = SourceRef(file=ep.file_name, line_start=min((e.source_line for e in evs), default=0),
                    line_end=max((e.source_line for e in evs), default=0), event_ids=[e.event_id for e in evs])
    return Segment(order=order, episode=ep.number, start=round(start, 2), end=round(end, 2), start_ts=fmt_ts(start),
                   end_ts=fmt_ts(end), duration=round(end - start, 2), source=src, reason=reason)


def _moment(m, ep: int) -> Moment:
    return Moment(text=m.text, episode=ep, time=m.time if m.time else 0.0, ts=fmt_ts(m.time), event_id=m.event_id,
                  kind=m.kind, labels=m.labels)


def _density(ep: Episode, an: EpisodeAnalysis, a: float, b: float) -> tuple[float, dict[str, float]]:
    evs = [e for e in ep.events if a <= e.start < b]
    labels: dict[str, float] = {}
    for e in evs:
        for k, v in an.signals[e.event_id].labels.items():
            labels[k] = max(labels.get(k, 0), v)
    beats = sum(1 for e in evs if e.kind != "CAMERA")
    return min(2.0, beats / max(b - a, 1) * 4), labels


def assemble(segs: list[Segment], kind: str, eps: dict[int, Episode], ans: dict[int, EpisodeAnalysis]) -> Promo | None:
    first, last = segs[0], segs[-1]
    h_ep, c_ep = eps[first.episode], eps[last.episode]
    h = hook_at(h_ep, ans[first.episode], first.start)
    # the cliffhanger must sit inside the last segment
    c = cliff_at(c_ep, ans[last.episode], last.end, window=min(4.0, last.duration))
    if not h or not c:
        return None
    hook_m = _moment(h, first.episode)
    cliff_m = _moment(c, last.episode)
    cliff_m.time = c.time if c.time <= last.end else last.end
    if c.kind in ("SFX", "CAMERA"):
        # show the editor the last thing the viewer actually hears, plus the visual/sound beat
        spoken = [e for e in c_ep.events if e.kind == "DIALOGUE" and last.start <= e.start < last.end]
        if spoken:
            cliff_m.text = f"“{spoken[-1].text}” → {c.text}"
    labels: dict[str, float] = {}
    dens = 0.0
    for s in segs:
        d, lab = _density(eps[s.episode], ans[s.episode], s.start, s.end)
        dens += d * s.duration
        for k, v in lab.items():
            labels[k] = max(labels.get(k, 0), v)
    total = round(sum(s.duration for s in segs), 2)       # gaps between segments are NOT counted
    dens /= max(total, 1)
    sweet = 0.5 if SWEET[0] <= total <= SWEET[1] else 0.0
    rule = 0.45 * h.strength + 0.45 * c.strength + 0.3 * dens + sweet
    if kind != "continuous":
        rule -= 0.3        # stitched cuts carry a coherence risk
    return Promo(promo_id=promo_id_for(segs), kind=kind, segments=segs, duration=total, hook=hook_m,
                 cliffhanger=cliff_m, labels=labels, rule_hook=h.strength, rule_cliff=c.strength,
                 rule_score=round(rule, 3))


def _cut_ends(ep: Episode) -> list[float]:
    return sorted(t for t in ({e.end for e in ep.events if e.kind != "CAMERA"} | {ep.duration})
                  if not mid_line(ep, t, as_start=False))


def _cut_starts(ep: Episode) -> list[float]:
    return sorted(t for t in ({0.0} | {e.start for e in ep.events}) if not mid_line(ep, t, as_start=True))


def _nearest(points: list[float], target: float, lo: float, hi: float) -> float | None:
    pool = [p for p in points if lo <= p <= hi]
    return min(pool, key=lambda p: abs(p - target)) if pool else None


def continuous(ep: Episode, an: EpisodeAnalysis, eps, ans, per_episode: int = 14) -> list[Promo]:
    ends = _cut_ends(ep)
    out = []
    for h in hook_candidates(ep, an, top=8):
        for t in ends:
            if MIN_S <= t - h.time <= MAX_S:
                seg = make_segment(ep, h.time, t, 1, "continuous stretch from hook to cliffhanger")
                p = assemble([seg], "continuous", eps, ans)
                if p:
                    out.append(p)
    out.sort(key=lambda p: -p.rule_score)
    return out[:per_episode]


def multi_segment(ep: Episode, an: EpisodeAnalysis, eps, ans) -> list[Promo]:
    ends, starts = _cut_ends(ep), _cut_starts(ep)
    out = []
    for h in hook_candidates(ep, an, top=3):
        for c in cliff_candidates(ep, an, top=3):
            if c.time - h.time <= MAX_S:
                continue      # a continuous cut already covers it
            e1 = _nearest(ends, h.time + 14, h.time + 8, h.time + 22)
            if e1 is None:
                continue
            len1 = e1 - h.time
            s2 = _nearest(starts, c.time - (40 - len1), c.time - 30, c.time - 8)
            if s2 is None or s2 < e1 + 3:
                continue
            segs = [make_segment(ep, h.time, e1, 1, "opening hook"),
                    make_segment(ep, s2, c.time, 2, "jump ahead to the cliffhanger (slow middle skipped)")]
            p = assemble(segs, "multi_segment", eps, ans)
            if p:
                out.append(p)
    return sorted(out, key=lambda p: -p.rule_score)[:3]


def cross_episode(eps: dict[int, Episode], ans: dict[int, EpisodeAnalysis], top: int = 20) -> list[Promo]:
    nums = sorted(eps)
    out = []
    for n in nums:
        a = eps[n]
        a_ends = _cut_ends(a)
        for h in hook_candidates(a, ans[n], top=2):
            e1 = _nearest(a_ends, h.time + 16, h.time + 9, h.time + 24)
            if e1 is None:
                continue
            for m in (n + 1, n + 2):
                if m not in eps:
                    continue
                b = eps[m]
                b_starts = _cut_starts(b)
                for c in cliff_candidates(b, ans[m], top=2):
                    len1 = e1 - h.time
                    s2 = _nearest(b_starts, c.time - (42 - len1), c.time - 30, c.time - 8)
                    if s2 is None:
                        continue
                    segs = [make_segment(a, h.time, e1, 1, f"hook from episode {n}"),
                            make_segment(b, s2, c.time, 2, f"escalation and cliffhanger from episode {m}")]
                    p = assemble(segs, "cross_episode", eps, ans)
                    if p:
                        out.append(p)
    out.sort(key=lambda p: -p.rule_score)
    keep: list[Promo] = []
    used: set[int] = set()
    for p in out:                  # at most one trailer per starting episode
        if p.segments[0].episode not in used:
            keep.append(p)
            used.add(p.segments[0].episode)
        if len(keep) >= top:
            break
    return keep


def generate_all(episodes: list[Episode], analyses: dict[int, EpisodeAnalysis]) -> list[Promo]:
    eps = {e.number: e for e in episodes}
    out: list[Promo] = []
    for ep in episodes:
        out += continuous(ep, analyses[ep.number], eps, analyses)
        out += multi_segment(ep, analyses[ep.number], eps, analyses)
    out += cross_episode(eps, analyses)
    seen, uniq = set(), []
    for p in out:
        if p.promo_id not in seen:
            seen.add(p.promo_id)
            uniq.append(p)
    return uniq
