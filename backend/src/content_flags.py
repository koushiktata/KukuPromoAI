"""Content-review signals for promos (not legal or platform-policy decisions).

Only event TEXT is scanned, never the writer's emotion tags: e.g. a "(Passionate, Defiant)"
tag is not sexual content. Patterns need a human target where it matters
("a heavy wet slap as the book hits the puddle" is not violence).
"""
from __future__ import annotations

import hashlib
import re

from .models import ContentFlag, Promo
from .parser import Episode, fmt_ts

PERSON = r"(her|him|juliana|alexander|catherine|clarissa|the (girl|maid|boy|woman|man|prisoner))"
RULES: list[tuple[str, str, str, float]] = [
    # type, pattern, severity, confidence
    ("graphic_violence", r"\b(blood(y|ied|-streaked|-soaked)?|bleed\w*|gash|lacerat\w*|stab\w*|gore|branding|red-hot|searing|burnt? flesh|torn (hands|flesh))\b", "high", 0.7),
    ("physical_abuse", rf"\b(strikes?|struck|slap(s|ped)?|backhand\w*|kick\w*|shove\w*|chok\w*|drag(s|ged)?)\s+{PERSON}\b|\briding crop\b|\bwhip\w*\b|\blash(es|ed)\b", "high", 0.75),
    ("sexual_content", r"\b(illicit (passion|intimacy|affair)|intimate assurances|seduc\w*|lovers?\b|undress\w*|passionate(ly)? kiss\w*|in (his|her) bed)\b", "medium", 0.6),
    ("nudity_reference", r"\b(naked|nude|bare (chest|torso|skin|shoulders?|back)|shirtless|disrobe\w*)\b", "medium", 0.6),
    ("threat", r"\b(i('ll| will) (kill|burn|destroy)|you will (hang|burn|die)|hang(ed)? (you|her|him)|gallows|execution|be executed|burn (you|her) alive)\b", "medium", 0.7),
    ("harassment", r"\b(worthless|witch\b|whore|harlot|filth\w*|plainness|low value|beggar|wretch)\b", "low", 0.55),
    ("child_endangerment", r"\b(child|boy|brother|son)\b.*\b(gaol|prison|die|dying|fever|hang)\b|\b(gaol|prison)\b.*\b(child|brother)\b", "medium", 0.5),
    ("poisoning", r"\b(arsenic|poison(ed|ing)?)\b", "low", 0.6),
    ("weapon", r"\b(sword|dagger|knife|blade|pistol|musket)\b", "low", 0.5),
]


def detect_flags(episodes: list[Episode], merge_window: float = 12.0) -> list[ContentFlag]:
    flags: list[ContentFlag] = []
    for ep in episodes:
        open_by_type: dict[str, ContentFlag] = {}
        for ev in ep.events:
            if ev.kind not in ("DIALOGUE", "ACTION", "CAMERA"):
                continue
            for ftype, pat, sev, conf in RULES:
                if not re.search(pat, ev.text, re.I):
                    continue
                cur = open_by_type.get(ftype)
                if cur and ev.start - cur.end <= merge_window:
                    cur.end = max(cur.end, ev.end)
                    cur.event_ids.append(ev.event_id)
                    cur.confidence = round(min(0.95, cur.confidence + 0.05), 2)
                    continue
                fid = "F" + hashlib.sha1(f"{ep.number}:{ftype}:{ev.event_id}".encode()).hexdigest()[:9]
                f = ContentFlag(flag_id=fid, flag_type=ftype, episode=ep.number, start=ev.start, end=ev.end,
                                ts=fmt_ts(ev.start), snippet=ev.text[:90] + ("…" if len(ev.text) > 90 else ""),
                                severity=sev, confidence=conf, event_ids=[ev.event_id])
                flags.append(f)
                open_by_type[ftype] = f
    return flags


def flags_for_promo(p: Promo, flags: list[ContentFlag]) -> list[str]:
    out = []
    for f in flags:
        for s in p.segments:
            if f.episode == s.episode and f.start < s.end and f.end > s.start:
                out.append(f.flag_id)
                break
    return out
