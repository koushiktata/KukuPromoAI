"""Multi-LLM judge panel."""
import pytest

from backend.llm.base import JudgeCandidate, JudgeRequest, JudgeResponse, JudgeVerdict, LLMProvider
from backend.llm.ensemble import EnsembleProvider, agreement_level


class Fake(LLMProvider):
    def __init__(self, name, score=None, fail=False):
        self.name, self.score, self.fail = name, score, fail

    def judge(self, req):
        if self.fail:
            raise RuntimeError("rate limited")
        s = self.score
        return JudgeResponse(provider=self.name, raw="{}", verdicts=[JudgeVerdict(
            candidate_id=c.candidate_id, verdict="Postable" if s >= 3.5 else "Skip", comment=f"{self.name} says hi",
            why_it_works=f"why from {self.name}",
            scores={"hook": s, "cliffhanger": s, "standalone": s, "emotion": s, "coherence": s}) for c in req.candidates])


REQ = JudgeRequest(episode=1, story_so_far="", logline="", candidates=[
    JudgeCandidate(candidate_id="P1", kind="continuous", duration=30, transcript="", hook_text="", cliff_text="")])


def test_panel_averages_scores_and_reports_each_model():
    r = EnsembleProvider([Fake("groq:a", 4.0), Fake("gemini:b", 3.5)]).judge(REQ)
    v = r.verdicts[0]
    assert v.scores["hook"] == 3.75 and v.agreement == "high"
    assert [m["model"] for m in v.panel] == ["groq:a", "gemini:b"] and v.panel[0]["overall"] == 4.0
    assert "groq" in r.provider and "gemini" in r.provider


def test_panel_flags_disagreement():
    v = EnsembleProvider([Fake("groq:a", 5.0), Fake("gemini:b", 2.0)]).judge(REQ).verdicts[0]
    assert v.agreement == "low"
    assert agreement_level(0.5) == "high" and agreement_level(1.5) == "medium" and agreement_level(3) == "low"


def test_panel_survives_one_failing_model():
    r = EnsembleProvider([Fake("groq:a", fail=True), Fake("gemini:b", 4.0)]).judge(REQ)
    assert r.verdicts[0].scores["hook"] == 4.0 and "rate limited" in r.raw


def test_panel_fails_only_when_every_model_fails():
    with pytest.raises(RuntimeError, match="every LLM"):
        EnsembleProvider([Fake("a", fail=True), Fake("b", fail=True)]).judge(REQ)


def test_make_providers_rules(monkeypatch):
    from backend.config import Settings
    from backend.llm.configurable_provider import make_providers
    from backend.llm.mock_provider import MockProvider
    s = Settings()
    assert isinstance(make_providers(s, ["mock"]), MockProvider)
    with pytest.raises(ValueError):
        make_providers(s, ["mock", "groq"])
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x" * 5)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" * 6)
    panel = make_providers(s, ["groq", "gemini", "groq"], {"groq": "llama-x"})
    assert isinstance(panel, EnsembleProvider) and len(panel.providers) == 2
    assert panel.providers[0].model == "llama-x"
    assert "gsk_x" not in str(panel.describe())
