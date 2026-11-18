"""Judge panel: several LLMs score the same candidates in parallel; scores are averaged.
A model that fails is skipped (the others still count). Big disagreement is surfaced, not hidden."""
from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .base import JudgeRequest, JudgeResponse, JudgeVerdict, LLMProvider

CRITERIA = ("hook", "cliffhanger", "standalone", "emotion", "coherence")


def agreement_level(spread: float) -> str:
    return "high" if spread < 1.0 else "medium" if spread < 2.0 else "low"


class EnsembleProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]):
        if len(providers) < 2:
            raise ValueError("an ensemble needs at least two providers")
        self.providers = providers
        self.name = "panel[" + ", ".join(p.name for p in providers) + "]"

    def describe(self) -> dict:
        return {"provider": self.name, "members": [p.describe() for p in self.providers]}

    def judge(self, req: JudgeRequest) -> JudgeResponse:
        def call(p: LLMProvider):
            try:
                return p.name, p.judge(req), None
            except Exception as e:  # one model failing must not sink the panel
                return p.name, None, str(e)[:200]

        with ThreadPoolExecutor(max_workers=len(self.providers)) as pool:
            results = list(pool.map(call, self.providers))
        ok = [(n, r) for n, r, e in results if r is not None]
        errors = {n: e for n, _, e in results if e}
        if not ok:
            raise RuntimeError("every LLM in the panel failed: " + "; ".join(f"{n}: {e}" for n, e in errors.items()))

        by_id: dict[str, list[tuple[str, JudgeVerdict]]] = {}
        for name, resp in ok:
            for v in resp.verdicts:
                by_id.setdefault(v.candidate_id, []).append((name, v))
        merged = []
        for cid, votes in by_id.items():
            scored = [(n, v) for n, v in votes if v.scores]
            avg, spread = None, 0.0
            if scored:
                avg = {}
                for c in CRITERIA:
                    vals = [v.scores[c] for _, v in scored if c in v.scores]
                    if vals:
                        avg[c] = round(sum(vals) / len(vals), 2)
                        spread = max(spread, max(vals) - min(vals))
            verdicts = Counter(v.verdict for _, v in votes if v.verdict)
            panel = [{"model": n, "scores": v.scores or {}, "verdict": v.verdict, "comment": v.comment[:160],
                      "overall": round(sum(v.scores.values()) / len(v.scores), 2) if v.scores else None}
                     for n, v in votes]
            best_why = next((v.why_it_works for _, v in votes if v.why_it_works), "")
            merged.append(JudgeVerdict(
                candidate_id=cid, scores=avg, why_it_works=best_why,
                verdict=verdicts.most_common(1)[0][0] if verdicts else "",
                comment=" | ".join(f"{n.split(':')[0]}: {v.comment}" for n, v in votes if v.comment)[:300],
                panel=panel, agreement=agreement_level(spread) if len(scored) > 1 else ""))
        raw = json.dumps({"members": [n for n, _ in ok], "errors": errors,
                          "raw": {n: r.raw for n, r in ok}})
        return JudgeResponse(verdicts=merged, raw=raw, provider=self.name)
