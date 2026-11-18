import pytest

from backend.config import settings
from backend.src.content_flags import detect_flags, flags_for_promo
from backend.src.models import ValidationStatus, promo_id_for
from backend.src.promo_generator import assemble, generate_all, make_segment
from backend.src.ranking import is_duplicate, overlap_ratio, rank
from backend.src.scoring import Calibrator, apply_scores, heuristic_scores, weighted
from backend.src.spoiler_analysis import categorize, find_secrets
from backend.src.validation import validate_promo


@pytest.fixture(scope="module")
def scored(episodes, analyses):
    eps = {e.number: e for e in episodes}
    ps = generate_all(episodes, analyses)
    cal = Calibrator([p.rule_hook for p in ps], [p.rule_cliff for p in ps])
    for p in ps:
        apply_scores(p, heuristic_scores(p, eps, analyses, cal), settings.weights)
        p.validation = validate_promo(p, eps)
    return eps, ps


def test_generation_uses_real_boundaries_and_20_60s(scored):
    eps, ps = scored
    assert ps
    kinds = {p.kind for p in ps}
    assert "continuous" in kinds and "cross_episode" in kinds
    for p in ps:
        assert 20 <= p.duration <= 60
        for s in p.segments:
            starts, ends = eps[s.episode].boundaries()
            assert any(abs(s.start - x) < 0.011 for x in starts)
            assert any(abs(s.end - x) < 0.011 for x in ends)
            assert s.source and s.source.event_ids and s.source.line_start > 0


def test_hook_within_first_3s(scored):
    _, ps = scored
    for p in ps:
        assert 0 <= p.hook.time - p.segments[0].start <= 3.0 + 1e-6


def test_duration_excludes_gaps(episodes, analyses):
    eps = {e.number: e for e in episodes}
    ep = eps[1]
    s1 = make_segment(ep, ep.events[0].start, ep.events[6].end, 1, "a")
    s2 = make_segment(ep, ep.events[14].start, ep.events[20].end, 2, "b")
    p = assemble([s1, s2], "multi_segment", eps, analyses)
    assert p.duration == pytest.approx(s1.duration + s2.duration, abs=0.01)
    assert p.duration < s2.end - s1.start


def test_validation_rejects_fabricated_timestamps(scored):
    eps, ps = scored
    p = ps[0].model_copy(deep=True)
    p.segments[0].start += 0.37                                # not a real event boundary
    p.duration = round(sum(s.end - s.start for s in p.segments), 2)
    v = validate_promo(p, eps)
    assert v.status == ValidationStatus.INVALID
    assert not next(c for c in v.checks if c.name == "source_timestamps_exist").passed


def test_validation_rejects_bad_duration_order_and_episode(scored):
    eps, ps = scored
    short = ps[0].model_copy(deep=True)
    seg = short.segments[0]
    seg.end = next(e.end for e in eps[seg.episode].events if e.end > seg.start + 5)
    short.duration = round(seg.end - seg.start, 2)
    assert validate_promo(short, eps).status == ValidationStatus.INVALID
    multi = next(p for p in ps if p.kind == "cross_episode").model_copy(deep=True)
    multi.segments = list(reversed(multi.segments))
    for i, s in enumerate(multi.segments, 1):
        s.order = i
    assert not next(c for c in validate_promo(multi, eps).checks if c.name == "segment_order").passed
    ghost = ps[0].model_copy(deep=True)
    ghost.segments[0].episode = 99
    assert validate_promo(ghost, eps).status == ValidationStatus.INVALID


def test_scores_are_1_to_5_and_weighted(scored):
    _, ps = scored
    for p in ps:
        for k in ("hook", "cliffhanger", "standalone", "emotion", "coherence", "overall"):
            assert 1 <= getattr(p.scores, k) <= 5
    assert weighted({k: 5 for k in settings.weights}, settings.weights) == 5
    assert weighted({"hook": 5, "cliffhanger": 1, "standalone": 1, "emotion": 1, "coherence": 1},
                    {"hook": 1, "cliffhanger": 0, "standalone": 0, "emotion": 0, "coherence": 0}) == 5


def test_llm_scores_are_blended_not_trusted_blindly(scored):
    _, ps = scored
    p = ps[0].model_copy(deep=True)
    heur = {"hook": 2, "cliffhanger": 2, "standalone": 2, "emotion": 2, "coherence": 2}
    apply_scores(p, heur, settings.weights, {"hook": 5, "cliffhanger": 5}, "test-llm")
    assert p.scores.hook == pytest.approx(0.6 * 5 + 0.4 * 2)
    assert p.scores.standalone == 2 and "blended" in p.scores.source


def test_ranking_groups_duplicates_as_alternatives(scored):
    _, ps = scored
    heads = rank([p.model_copy(deep=True) for p in ps])
    assert len(heads) < len(ps)
    assert any(h.alternatives for h in heads)
    for i, a in enumerate(heads):
        for b in heads[i + 1:]:
            assert not is_duplicate(a, b)
    ranks = [h.rank for h in heads if h.rank]
    assert ranks == list(range(1, len(ranks) + 1))
    assert overlap_ratio(heads[0], heads[0]) == pytest.approx(1.0)


def test_invalid_promos_get_no_rank(scored):
    eps, ps = scored
    bad = ps[0].model_copy(deep=True)
    bad.promo_id = "Pbad"
    bad.validation.status = ValidationStatus.INVALID
    heads = rank([bad])
    assert heads[0].rank is None and heads[0].posting_priority == "Do not post"


def test_stable_promo_ids(scored):
    _, ps = scored
    assert promo_id_for(ps[0].segments) == ps[0].promo_id


def test_secrets_and_spoiler_classification(scored, episodes):
    eps, ps = scored
    secrets = find_secrets(episodes)
    themes = {s.theme for s in secrets}
    assert "hidden_identity" in themes and all(s.evidence and s.ai_generated for s in secrets)
    spoiler = next(p for p in ps if any("rightful duke" in e.text for s in p.segments
                                        for e in eps[s.episode].events if s.start <= e.start < s.end))
    cat = categorize(spoiler, eps, secrets)
    assert cat.spoiler_secret_ids and not cat.new_viewer
    assert "secrets" in cat.explanation


def test_content_flags_use_text_not_tags(episodes, scored):
    _, ps = scored
    flags = detect_flags(episodes)
    types = {f.flag_type for f in flags}
    assert "physical_abuse" in types and "threat" in types
    assert not any("book lands" in f.snippet for f in flags if f.flag_type == "physical_abuse")
    assert "sexual_content" not in types                       # "(Defiant, Passionate)" is only a tag
    assert any(flags_for_promo(p, flags) for p in ps)
