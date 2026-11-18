"""Show secrets (AI-generated, must be verified by an editor) + audience categories for promos.

Secrets are found from screenplay evidence: genre-level "secret themes" (hidden identity,
poisoning, frame-up...) are matched against dialogue/action lines and loglines. A theme only
becomes a secret if at least two screenplay events support it; the evidence is kept.
An LLM provider can add/rename secrets, but each one must still be backed by evidence in code.
"""
from __future__ import annotations

import hashlib
import re

from .models import Category, Promo, Secret
from .parser import Episode, fmt_ts

THEMES: dict[str, dict] = {
    "hidden_identity": {"title": "Hidden identity / true heir", "severity": "high",
                        "pat": r"\b(the (true |rightful )?duke|rightful (heir|duke)|true identity|lost son|ducal|my son is alive|heir to)\b"},
    "return_from_dead": {"title": "A presumed-dead character is alive", "severity": "high",
                         "pat": r"\b(presumed[- ]dead|return(s|ed)? from the dead|declared (me|him) dead|dead (heir|duke)|thought (you were|he was) dead|you're alive|he is alive|still alive)\b"},
    "secret_mission": {"title": "A secret Crown mission / spy plot", "severity": "medium",
                       "pat": r"\b(classified|crown mission|spies|spy\b|informant|military secrets)\b"},
    "poisoning": {"title": "Secret poisoning", "severity": "medium",
                  "pat": r"\b(poison(ed|ing)?|arsenic|antidote)\b"},
    "frame_up": {"title": "Frame-up / false accusation", "severity": "medium",
                 "pat": r"\b(fram(e|ed|ing)|false testimony|planted|witchcraft|accuse[ds]? of)\b"},
    "mastermind": {"title": "Who is secretly behind the attacks", "severity": "medium",
                   "pat": r"\b(who sent you|mastermind|paid us|behind (this|it all)|on whose orders|confess)\b"},
    "usurpation": {"title": "Usurpers plotting to seize a title", "severity": "medium",
                   "pat": r"\b(usurp\w*|seize the (ducal )?title|claim the title|stole my (home|title|house)|treason\w*)\b"},
    "past_relationship": {"title": "A hidden past relationship", "severity": "medium",
                          "pat": r"\b(our past|what we had|you (once )?loved me|we were (once )?(lovers|betrothed)|past love)\b"},
    "illicit_affair": {"title": "Illicit affair", "severity": "high",
                       "pat": r"\b(illicit|affair|lovers?|passion (between|with)|scandalous)\b"},
    "marriage_invalid": {"title": "Marriage declared invalid", "severity": "high",
                         "pat": r"\b(invalid\w*|annul\w*|no (royal |crown )?licen[cs]e|without (leave|licen[cs]e)|licensed clergyman|not (legally )?bind\w*|void)\b"},
}


def find_secrets(episodes: list[Episode], min_support: int = 2) -> list[Secret]:
    out: list[Secret] = []
    for theme, cfg in THEMES.items():
        rx = re.compile(cfg["pat"], re.I)
        hits = []
        for ep in episodes:
            # writer loglines / continuity notes are part of the source file and count as evidence
            for field in ("logline", "continuity"):
                txt = getattr(ep, field)
                if txt and rx.search(txt):
                    hits.append((ep, None, field, txt))
            for ev in ep.events:
                if ev.kind in ("DIALOGUE", "ACTION") and rx.search(ev.text):
                    hits.append((ep, ev, ev.kind.lower(), ev.text))
        if len(hits) < min_support:
            continue
        hits.sort(key=lambda h: (h[0].number, h[1].start if h[1] else -1))
        first_ep = hits[0][0]
        lines_first = [h for h in hits if h[1] is not None][:3]
        ev_list = [{"episode": ep.number, "ts": fmt_ts(ev.start) if ev else "logline" if f == "logline" else "notes",
                    "event_id": ev.event_id if ev else "", "source": f, "snippet": t[:110] + ("…" if len(t) > 110 else "")}
                   for ep, ev, f, t in (hits[:2] + [h for h in lines_first if h not in hits[:2]])[:4]]
        hits = [(h[0], h[1]) for h in hits]
        eps_hit = sorted({ep.number for ep, _ in hits})
        logline = first_ep.logline[:160] + ("…" if len(first_ep.logline) > 160 else "")
        sev = cfg["severity"]
        if first_ep.number >= len(episodes) * 0.6 and sev == "medium":
            sev = "high"          # late-story developments spoil more
        out.append(Secret(
            secret_id="S" + hashlib.sha1(theme.encode()).hexdigest()[:8], theme=theme,
            description=f"{cfg['title']} — first surfaces in Ep {first_ep.number} "
                        f"(appears in {len(eps_hit)} episodes). Context: {logline}",
            reveal_episode=first_ep.number, evidence=ev_list, severity=sev,
            confidence=round(min(0.9, 0.35 + 0.08 * len(hits)), 2), patterns=[cfg["pat"]]))
    return sorted(out, key=lambda s: s.reveal_episode)


def categorize(p: Promo, eps: dict[int, Episode], secrets: list[Secret]) -> Category:
    text = " ".join(e.text for s in p.segments for e in eps[s.episode].events
                    if s.start - 1e-6 <= e.start < s.end - 1e-6 and e.kind in ("DIALOGUE", "ACTION"))
    hits = [sec for sec in secrets
            if any(re.search(pt, text, re.I) for pt in sec.patterns) and max(p.episodes) >= sec.reveal_episode]
    major = [h for h in hits if h.severity in ("high", "medium")]
    sc = p.scores
    reasons = []
    new_viewer = (not major and sc.standalone >= 3.0 and sc.hook >= 3.0 and sc.cliffhanger >= 2.8)
    if new_viewer:
        reasons.append("strong hook, understandable cold, no known secret revealed")
    else:
        if major:
            reasons.append("touches show secrets: " + ", ".join(h.theme for h in major))
        if sc.standalone < 3.0:
            reasons.append(f"needs prior context (standalone {sc.standalone}/5)")
        if sc.hook < 3.0:
            reasons.append(f"hook too weak for cold viewers ({sc.hook}/5)")
    retarget = (bool(hits) or min(p.episodes) > 10) and sc.cliffhanger >= 3.0 and sc.emotion >= 3.0 \
        and sc.overall >= 3.6
    if retarget:
        reasons.append("works for existing viewers" + (" (contains spoilers)" if hits else " (later-story moment)"))
    if not new_viewer and not retarget:
        reasons.append("not recommended for either audience")
    return Category(new_viewer=new_viewer, retarget=retarget, spoiler_secret_ids=[h.secret_id for h in hits],
                    explanation="; ".join(reasons))
