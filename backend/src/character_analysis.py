"""Characters, aliases, relationships and cross-episode story context."""
from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from .nlp_analysis import EpisodeAnalysis
from .parser import Episode

SUFFIX_RE = re.compile(r"\s*\((V\.O\.|O\.S\.|OFF-SCREEN|CONT'D)\)\s*$", re.I)

# Alias table: screenplay header names -> canonical character. Each entry records why
# (evidence), because the same person is credited differently before their name is known.
ALIASES: dict[str, tuple[str, str]] = {
    "LADY JULIANA": ("JULIANA", "same character, title prefix"),
    "MYSTERIOUS BEARDED MAN": ("ALEXANDER", "the scarred stranger who proposes in Ep 3 is Juliana's husband Alexander (Ep 4-6 loglines)"),
    "THE BEARDED STRANGER": ("ALEXANDER", "same stranger, Ep 3-4"),
    "SCARRED BEARDED MAN": ("ALEXANDER", "same stranger"),
    "LADY IN GOLD GOWN": ("CLARISSA", "Ep 1 logline: Gerald leaves Juliana for her sister Clarissa at the altar"),
    "LADY CLARISSA": ("CLARISSA", "title prefix"),
    "THE FORMER GROOM": ("GERALD", "Ep 1 logline: fiancé Gerald"),
    "BLOND NOBLEMAN": ("RUPERT", "header 'BLOND NOBLEMAN (RUPERT)' appears in the scripts"),
    "BLOND NOBLEMAN (RUPERT)": ("RUPERT", "explicit in header"),
    "LADY CATHERINE": ("CATHERINE", "title prefix"),
    "NOBLE MATRIARCH": ("MATRIARCH", "same role"),
    "POLICE CONSTABLE": ("CONSTABLE", "same role"),
    "THE PRIEST": ("PRIEST", "same role"),
}


def canonical(name: str) -> str:
    n = SUFFIX_RE.sub("", name.strip().upper())
    return ALIASES.get(n, (n, ""))[0]


class CharacterProfile(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    lines: int = 0
    episodes: list[int] = Field(default_factory=list)
    first_episode: int = 0
    dominant_emotions: list[str] = Field(default_factory=list)


class Relationship(BaseModel):
    a: str
    b: str
    exchanges: int
    mean_sentiment: float
    episodes: list[int]


class StoryContext(BaseModel):
    characters: dict[str, CharacterProfile]
    relationships: list[Relationship]
    loglines: dict[int, str]
    alias_evidence: dict[str, str]

    def story_so_far(self, episode: int, window: int = 5) -> str:
        prev = [e for e in sorted(self.loglines) if episode - window <= e < episode]
        return "\n".join(f"Ep {e}: {self.loglines[e]}" for e in prev)

    def main_cast(self, n: int = 6) -> list[str]:
        return [c.name for c in sorted(self.characters.values(), key=lambda c: -c.lines)[:n]]


def build_context(episodes: list[Episode], analyses: dict[int, EpisodeAnalysis]) -> StoryContext:
    chars: dict[str, CharacterProfile] = {}
    emo_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pair_stats: dict[tuple[str, str], list] = defaultdict(lambda: [0, 0.0, set()])
    for ep in episodes:
        an = analyses.get(ep.number)
        prev = None
        for ev in ep.events:
            if ev.kind != "DIALOGUE":
                continue
            raw = SUFFIX_RE.sub("", ev.speaker)
            name = canonical(ev.speaker)
            c = chars.setdefault(name, CharacterProfile(name=name, first_episode=ep.number))
            c.lines += 1
            if raw != name and raw not in c.aliases:
                c.aliases.append(raw)
            if ep.number not in c.episodes:
                c.episodes.append(ep.number)
            for emo in ev.emotions:
                emo_counts[name][emo.lower()] += 1
            # adjacency = an exchange between two speakers
            if prev and prev[0] != name and ev.start - prev[1] < 5:
                key = tuple(sorted((prev[0], name)))
                st = pair_stats[key]
                st[0] += 1
                st[1] += an.signals[ev.event_id].sentiment if an else 0
                st[2].add(ep.number)
            prev = (name, ev.end)
    for name, c in chars.items():
        c.dominant_emotions = [e for e, _ in sorted(emo_counts[name].items(), key=lambda t: -t[1])[:4]]
    rels = [Relationship(a=a, b=b, exchanges=n, mean_sentiment=round(s / n, 3), episodes=sorted(eps))
            for (a, b), (n, s, eps) in pair_stats.items() if n >= 3]
    rels.sort(key=lambda r: -r.exchanges)
    return StoryContext(characters=chars, relationships=rels,
                        loglines={e.number: e.logline for e in episodes},
                        alias_evidence={k: f"{v[0]} — {v[1]}" for k, v in ALIASES.items()})


def character_history(ctx: StoryContext, name: str) -> dict:
    c = ctx.characters.get(canonical(name))
    if not c:
        return {"found": False, "name": name}
    rels = [r.model_dump() for r in ctx.relationships if c.name in (r.a, r.b)][:8]
    return {"found": True, **c.model_dump(), "relationships": rels,
            "episode_loglines": {e: ctx.loglines[e] for e in c.episodes[:6]}}
