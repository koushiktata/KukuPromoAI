"""NLP layer: sentiment, emotional intensity and dramatic-event detection.

Signals combined per event (not keywords alone):
  1. VADER sentiment (NLTK pretrained lexicon model) on the line text.
  2. Writer emotion tags from dialogue headers (e.g. "Furious, Shouting") mapped to arousal.
  3. Lexical cues per dramatic category (weighted patterns).
  4. Structure: question/exclamation, short punchy lines, speaker turn-taking,
     unanswered questions, SFX "stings", position at episode end.
  5. Local context: a sentiment drop vs. the previous few lines (a "turn").
Each detected label carries a confidence and the evidence event id, so every
conclusion can be traced back to the screenplay.
"""
from __future__ import annotations

import re
from functools import lru_cache

from pydantic import BaseModel, Field

from .parser import Episode, Event

# ---------- emotion-tag arousal (0..1) ----------
AROUSAL = {
    r"scream|shriek|roar|howl|bellow": 1.0,
    r"furious|enraged|livid|rage|seething|explod|murderous|savage|violent": 0.95,
    r"shout|yell|thunder|bark": 0.9,
    r"horrif|terrif|panic|frantic|hysteric|agon|anguish|devastat|sobbing|wail": 0.9,
    r"shock|gasp|stunned|disbelief|aghast|breathless": 0.85,
    r"desperate|pleading|begging|urgent|alarmed|fearful|afraid|trembling|shaken": 0.75,
    r"cruel|venom|menac|threat|sinister|vicious|sadistic|gloat|mock|sneer|taunt|spite|contempt|disdain": 0.75,
    r"outraged|accus|indignant|defiant|fierce|bitter|angry|harsh|biting|scath": 0.75,
    r"cold|icy|stern|commanding|authoritative|firm|resolute|blunt|sharp|smug|arrogant|haughty": 0.55,
    r"heartbroken|tearful|raw|broken|pained|hurt|grief|sorrow|choked": 0.7,
    r"whisper|low|quiet|soft|gentle|tender|warm|kind|calm|reassur|loving|fond|wistful": 0.25,
}

# ---------- dramatic categories ----------
CATEGORIES: dict[str, list[tuple[str, float]]] = {
    "betrayal": [(r"betray|abandon|cast (you|her|me) aside|left me|traitor|deceiv|lied to|behind (my|your) back|marrying me|chose her", 1.0)],
    "humiliation": [(r"humiliat|disgrace|shame|beneath|worthless|plain(ness)?|low value|beggar|scrub|on your knees|kneel|mud|mock|laugh(ing|s)? at|whisper(ing)? and", 0.9)],
    "revelation": [(r"truth|reveal|secret|identity|who (you|he|she) really|the duke|(rightful|true) (duke|heir|duchess)|i am (the|his|her|your) (son|heir|duke|daughter|mother)|duchess|heir|alive|presumed dead|my son|crest|signet|arsenic|poison(ed|ing)|confess|it was (you|him|her)", 1.0)],
    "unexpected_arrival": [(r"bursts? (in|open|through)|doors? (fly|burst|slam|creak|crack)|storms? in|enters|arrives?|appears|steps (out|forward|into)|emerg|silhouette|explosion", 0.9)],
    "threat": [(r"you will (pay|hang|burn|die|regret)|i('ll| will) (kill|destroy|ruin|burn)|or (else|watch)|hang|execut|gallows|burn (you|her|it)|red-hot|iron|blade|sword|dagger|knife|arrest", 1.0)],
    "confrontation": [(r"how dare|get out|stand aside|step away|unhand|let (her|him|me) go|you have no right|enough|silence!|stop", 0.9)],
    "violence": [(r"strikes?|struck|slap(s|ped)? (her|him|juliana|across)|punch|grab(s|bed)? (her|him)|seiz|drag|chok|wound|blood|bleed|stab|lash|whip|riding crop|shove|throws? (her|him)", 1.0)],
    "romance": [(r"love|marry|wife|husband|proposal|embrace|kiss|hold(s|ing)? her|my bride|vow|heart", 0.6)],
    "family_conflict": [(r"father|mother|sister|stepmother|disown|inheritance|family|daughter|son\b|brother", 0.6)],
    "revenge": [(r"reveng|veng|pay for|make them pay|reclaim|retribution|every(thing| last)|they will (pay|answer)", 0.9)],
    "power_shift": [(r"proclaim|rightful|salute|bow(s|ed)? (to|before)|kneel(s)? before|by order|the crown|seize (the|his) title|usurp|guards? refuse", 0.9)],
    "emotional_breakdown": [(r"sob|weep|tears|cries|crying|breaks down|collaps|trembl|shaking", 0.7)],
    "suspense": [(r"ominous|dread|tension|silence|shadow|lurk|watch(ing|es) from|hidden|unaware|cliffhanger|sting|cut to black|freezes|holds (her|his) breath", 0.8)],
}
RESOLUTION = re.compile(r"embrace|smil|laugh|relief|peace|gently|tender|warm|thank|sleeps|safe now|rest|kiss(es)? the crown", re.I)


class EventSignal(BaseModel):
    event_id: str
    start: float
    end: float
    sentiment: float          # VADER compound -1..1
    arousal: float            # 0..1
    labels: dict[str, float] = Field(default_factory=dict)   # category -> confidence
    is_question: bool = False
    unanswered: bool = False
    punchy: bool = False


class EpisodeAnalysis(BaseModel):
    episode: int
    signals: dict[str, EventSignal]
    intensity_curve: list[tuple[float, float]]     # (time, rolling intensity)
    label_counts: dict[str, int]
    peak_moments: list[dict]


@lru_cache(maxsize=1)
def _vader():
    try:
        from nltk.sentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        sia.polarity_scores("test")
        return sia
    except Exception:   # lexicon missing -> neutral sentiment, other signals still work
        return None


NEG_WORDS = re.compile(r"\b(no|never|hate|kill|die|dead|death|blood|pain|cruel|worthless|shame|disgrace|betray\w*|liar|thief|"
                       r"witch|poison\w*|hang|burn\w*|curse\w*|filth\w*|beg\w*|fear|afraid|wrong|lost|alone|rot|nothing|"
                       r"traitor|monster|ruin\w*|destroy\w*|suffer\w*|scream\w*|sob\w*|tears?|wound\w*|chain\w*|dungeon)\b", re.I)
POS_WORDS = re.compile(r"\b(love|safe|thank\w*|beautiful|happy|joy|hope|home|warm|gentle|proud|honou?r|free|together|kind|"
                       r"bless\w*|peace|smil\w*|laugh\w*|dear|my wife|my husband|forever)\b", re.I)
NEG_TAGS = re.compile(r"cruel|furious|outraged|cold|mock|smug|sneer|venom|menac|bitter|angry|despera|horrif|devastat|"
                      r"heartbroken|trembl|scream|shout|accus|contempt|disdain|spite|threat|sinister", re.I)
POS_TAGS = re.compile(r"gentle|warm|tender|loving|kind|reassur|fond|soft|grateful|joy|relie|happy|hopeful|proud", re.I)


def _fallback_sentiment(text: str, emotions: list[str] | None = None) -> float:
    """Valence from word lists + writer emotion tags, used when the VADER lexicon is not installed."""
    neg, pos = len(NEG_WORDS.findall(text)), len(POS_WORDS.findall(text))
    tags = " ".join(emotions or [])
    neg += 1.5 * len(NEG_TAGS.findall(tags))
    pos += 1.5 * len(POS_TAGS.findall(tags))
    if neg == pos == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / (pos + neg + 1)))


def sentiment(text: str, emotions: list[str] | None = None) -> float:
    v = _vader()
    if v and text:
        try:
            return v.polarity_scores(text)["compound"]
        except LookupError:
            pass
    return _fallback_sentiment(text, emotions)


def sentiment_backend() -> str:
    v = _vader()
    try:
        if v:
            v.polarity_scores("ok")
            return "nltk-vader"
    except LookupError:
        pass
    return "builtin-lexicon+emotion-tags"


def tag_arousal(emotions: list[str]) -> float:
    best = 0.0
    for emo in emotions:
        e = emo.lower()
        for pat, val in AROUSAL.items():
            if re.search(pat, e):
                best = max(best, val)
    return best if best else (0.5 if emotions else 0.0)


def analyse_episode(ep: Episode) -> EpisodeAnalysis:
    signals: dict[str, EventSignal] = {}
    recent_sent: list[float] = []
    dialogue = [e for e in ep.events if e.kind == "DIALOGUE"]
    for ev in ep.events:
        text = ev.text
        s = sentiment(text, ev.emotions)
        a = tag_arousal(ev.emotions)
        if ev.kind != "DIALOGUE":
            # actions/camera: infer arousal from sentiment magnitude and dramatic verbs
            a = max(a, min(1.0, abs(s) * 0.8))
        is_q = ev.kind == "DIALOGUE" and text.rstrip(" .\"'").endswith("?")
        punchy = ev.kind == "DIALOGUE" and len(text.split()) <= 9 and text.rstrip("\"'").endswith(("!", "?", "..."))
        if text.count("!"):
            a = max(a, 0.7)
        labels: dict[str, float] = {}
        low = text.lower()
        for cat, pats in CATEGORIES.items():
            for pat, w in pats:
                if re.search(r"\b(?:" + pat + ")", low):
                    conf = w * 0.6
                    conf += 0.25 * a                       # emotion tag agrees
                    conf += 0.15 if s < -0.3 and cat not in ("romance",) else 0
                    labels[cat] = round(min(1.0, conf), 2)
        # sentiment turn: sharp drop vs recent context = dramatic turn even without keywords
        if recent_sent and ev.kind in ("DIALOGUE", "ACTION"):
            base = sum(recent_sent[-4:]) / len(recent_sent[-4:])
            if base - s > 0.8:
                labels["turn"] = round(min(1.0, (base - s) / 1.5), 2)
        if ev.kind in ("DIALOGUE", "ACTION"):
            recent_sent.append(s)
        if ev.kind == "SFX" and re.search(r"sting|swell|cliffhanger|ominous|drone|boom|thunder|crash", low):
            labels["suspense"] = max(labels.get("suspense", 0), 0.8)
        signals[ev.event_id] = EventSignal(event_id=ev.event_id, start=ev.start, end=ev.end, sentiment=round(s, 3),
                                           arousal=round(a, 2), labels=labels, is_question=is_q, punchy=punchy)

    # unanswered questions: no reply from a different speaker within 4s
    for i, d in enumerate(dialogue):
        sig = signals[d.event_id]
        if sig.is_question:
            reply = [x for x in dialogue[i + 1:] if x.start - d.end <= 4.0 and x.speaker != d.speaker]
            if not reply:
                sig.unanswered = True
                sig.labels["unanswered_question"] = 0.8

    # rolling intensity (5s windows)
    curve = []
    t, step = 0.0, 5.0
    while t < ep.duration:
        win = [signals[e.event_id] for e in ep.events if t <= e.start < t + step]
        val = max([w.arousal + 0.3 * len(w.labels) for w in win], default=0.0)
        curve.append((round(t, 1), round(min(val, 2.0), 2)))
        t += step
    counts: dict[str, int] = {}
    for s in signals.values():
        for k in s.labels:
            counts[k] = counts.get(k, 0) + 1
    by_id = {e.event_id: e for e in ep.events}
    peaks = sorted(signals.values(), key=lambda s: s.arousal + sum(s.labels.values()), reverse=True)[:5]
    peak_moments = [{"event_id": p.event_id, "time": p.start, "labels": p.labels,
                     "snippet": by_id[p.event_id].text[:100]} for p in peaks]
    return EpisodeAnalysis(episode=ep.number, signals=signals, intensity_curve=curve,
                           label_counts=counts, peak_moments=peak_moments)


def search_moments(episodes: list[Episode], analyses: dict[int, EpisodeAnalysis], query: str, limit: int = 20) -> list[dict]:
    """Find events by dramatic label (e.g. 'betrayal') or free text."""
    q = query.lower().strip()
    out = []
    for ep in episodes:
        an = analyses.get(ep.number)
        for ev in ep.events:
            sig = an.signals.get(ev.event_id) if an else None
            score = 0.0
            if sig and q in sig.labels:
                score = sig.labels[q] + sig.arousal
            elif q and q in ev.text.lower():
                score = 0.5 + (sig.arousal if sig else 0)
            if score:
                out.append({"episode": ep.number, "event_id": ev.event_id, "time": ev.start, "score": round(score, 2),
                            "kind": ev.kind, "snippet": ev.text[:100]})
    return sorted(out, key=lambda x: -x["score"])[:limit]
