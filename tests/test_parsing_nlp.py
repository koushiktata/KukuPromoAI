import pytest

from backend.src.character_analysis import build_context, canonical, character_history
from backend.src.ingestion import inventory
from backend.src.nlp_analysis import analyse_episode, search_moments
from backend.src.parser import fmt_ts, parse_text, to_seconds
from conftest import make_episode


# ---------- timestamps ----------
@pytest.mark.parametrize("ts,sec", [("00:00.00", 0.0), ("01:23.45", 83.45), ("10:05.5", 605.5), ("02:00", 120.0)])
def test_to_seconds(ts, sec):
    assert to_seconds(ts) == pytest.approx(sec)


@pytest.mark.parametrize("bad", ["1:2", "aa:bb.cc", "01:75.00", ""])
def test_to_seconds_rejects_bad(bad):
    with pytest.raises(ValueError):
        to_seconds(bad)


def test_fmt_roundtrip():
    assert fmt_ts(to_seconds("02:18.50")) == "02:18.50"


# ---------- ingestion / parsing ----------
def test_parse_structure(episodes):
    ep = episodes[0]
    assert ep.number == 1 and ep.logline.startswith("Mara")
    assert len(ep.scenes) == 1 and ep.scenes[0].heading.startswith("INT. CHAPEL")
    kinds = {e.kind for e in ep.events}
    assert kinds == {"CAMERA", "DIALOGUE", "ACTION", "SFX"}
    d = next(e for e in ep.events if e.kind == "DIALOGUE" and "betray" in e.text)
    assert d.speaker == "MARA" and d.emotions == ["Furious", "Shouting"]
    assert d.source_line > 0 and not d.text.startswith('"')
    assert ep.issues == []
    assert ep.duration > 60


def test_events_sorted_and_ids_unique(episodes):
    for ep in episodes:
        starts = [e.start for e in ep.events]
        assert starts == sorted(starts)
        assert len({e.event_id for e in ep.events}) == len(ep.events)


def test_parser_reports_problems_instead_of_guessing():
    txt = make_episode(4).replace("Start: (00:03.50) | End: (00:05.50)", "Start: broken")
    txt = txt.replace("--- SCRIPT END ---", "")
    ep = parse_text(txt, "episode-005-x.txt")
    assert any("no timestamp" in i for i in ep.issues)
    assert any("SCRIPT END" in i for i in ep.issues)
    assert any("mismatch" in i for i in ep.issues)          # file says 5, header says 4


def test_inventory_detects_gaps_and_duplicates(episodes, data_dir):
    inv = inventory(episodes, data_dir)
    assert inv["files_found"] == 3 and inv["missing_episodes"] == []
    dup = inventory(episodes + [episodes[0]], data_dir)
    assert dup["duplicate_episode_numbers"] == [1]
    gap = inventory([episodes[0], episodes[2]], data_dir)
    assert gap["missing_episodes"] == [2]


# ---------- NLP ----------
def test_dramatic_event_detection(episodes, analyses):
    ep, an = episodes[0], analyses[1]
    def labels_for(snippet):
        ev = next(e for e in ep.events if snippet in e.text)
        return an.signals[ev.event_id].labels
    assert "betrayal" in labels_for("Because he is marrying me")
    assert "violence" in labels_for("strikes her across the face")
    assert "threat" in labels_for("you will hang")
    assert "unexpected_arrival" in labels_for("doors burst open")
    assert "revelation" in labels_for("rightful duke")


def test_word_boundaries_avoid_false_matches():
    from backend.src.parser import parse_text
    txt = make_episode(7).replace("Look at the altar.", "People change their minds.")
    ep = parse_text(txt, "episode-007.txt")
    an = analyse_episode(ep)
    ev = next(e for e in ep.events if "change their minds" in e.text)
    assert "threat" not in an.signals[ev.event_id].labels     # 'hang' inside 'change'


def test_unanswered_question_and_arousal(episodes, analyses):
    ep, an = episodes[0], analyses[1]
    q = next(e for e in ep.events if "Will you fight them all?" in e.text)
    assert an.signals[q.event_id].unanswered
    shout = next(e for e in ep.events if "How dare you" in e.text)
    calm = next(e for e in ep.events if "Look at the altar" in e.text)
    assert an.signals[shout.event_id].arousal > an.signals[calm.event_id].arousal


def test_search_moments(episodes, analyses):
    res = search_moments(episodes, analyses, "betrayal")
    assert res and all(r["episode"] in (1, 2, 3) for r in res)


# ---------- characters ----------
def test_character_aliases_and_relationships(episodes, analyses):
    assert canonical("LADY JULIANA (V.O.)") == "JULIANA"
    assert canonical("MYSTERIOUS BEARDED MAN") == "ALEXANDER"
    ctx = build_context(episodes, analyses)
    assert "MARA" in ctx.characters and ctx.characters["MARA"].episodes == [1, 2, 3]
    assert any({r.a, r.b} == {"MARA", "SISTER"} for r in ctx.relationships)
    h = character_history(ctx, "mara")
    assert h["found"] and h["lines"] > 0
    assert "Ep 1" in ctx.story_so_far(2)
