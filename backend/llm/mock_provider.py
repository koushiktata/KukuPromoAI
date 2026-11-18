"""Deterministic, offline 'judge'. Writes the why/verdict text from the NLP labels and leaves the
numeric scores to the rule engine (it returns scores=None, so nothing is double counted)."""
from __future__ import annotations

import json

from .base import JudgeRequest, JudgeResponse, JudgeVerdict, LLMProvider

HOOK_PHRASE = {
    "betrayal": "a public betrayal", "humiliation": "an underdog being humiliated", "violence": "sudden physical danger",
    "threat": "a life-or-death threat", "revelation": "a secret starting to surface", "confrontation": "a heated face-off",
    "unexpected_arrival": "someone bursting into the scene", "power_shift": "a sudden reversal of power",
    "emotional_breakdown": "raw emotion", "revenge": "a vow of revenge", "turn": "a sharp emotional turn",
}
CLIFF_PHRASE = {
    "unanswered_question": "an unanswered question", "suspense": "a held, unresolved beat",
    "threat": "a threat that hasn't played out", "unexpected_arrival": "an arrival we don't see resolved",
    "revelation": "a reveal with no reaction yet", "violence": "violence about to land",
    "power_shift": "a power shift mid-swing", "confrontation": "a stand-off with no winner yet",
}


class MockProvider(LLMProvider):
    name = "mock-heuristic"

    def judge(self, req: JudgeRequest) -> JudgeResponse:
        out = []
        for c in req.candidates:
            labs = c.labels
            hook = next((HOOK_PHRASE[l] for l in labs if l in HOOK_PHRASE), "a tense moment")
            cliff = next((CLIFF_PHRASE[l] for l in labs if l in CLIFF_PHRASE), "an open ending")
            h = c.heuristic
            overall = sum(h.values()) / max(len(h), 1)
            verdict = "Postable" if overall >= 3.8 else "Needs edit" if overall >= 3.0 else "Skip"
            weak = [k for k, v in h.items() if v < 3]
            comment = (f"{verdict}: opens on {hook}, cuts on {cliff}."
                       + (f" Weak on {', '.join(weak)}." if weak else ""))
            out.append(JudgeVerdict(
                candidate_id=c.candidate_id, scores=None,
                why_it_works=f"Opens on {hook} and cuts on {cliff}, so a cold viewer wants to know what happens next.",
                verdict=verdict, comment=comment))
        resp = JudgeResponse(verdicts=out, provider=self.name)
        resp.raw = json.dumps([v.model_dump() for v in out])
        return resp
