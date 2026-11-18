"""Promo discovery + LLM judging tools."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from ..harness.tool_registry import ToolRegistry
from ..llm.base import JudgeCandidate, JudgeRequest
from ..llm.mock_provider import MockProvider
from ..src.candidate_detection import cliff_candidates, hook_candidates
from ..src.models import Promo
from ..src.promo_generator import continuous, cross_episode, multi_segment
from ..src.ranking import is_duplicate
from ..src.scoring import Calibrator, apply_scores, heuristic_scores
from .screenplay_tools import Empty, EpisodeIn


class MomentsOut(BaseModel):
    episode: int
    moments: list[dict]


class GenOut(BaseModel):
    episode: int = 0
    generated: int
    kinds: dict[str, int]


class ScoreIn(BaseModel):
    stage: str = Field(pattern="^(heuristic|final)$")


class ScoreOut(BaseModel):
    scored: int
    judged: int = 0
    mean_overall: float


class JudgeOut(BaseModel):
    episode: int
    judged: int
    provider: str
    needs_review: bool = False


def _promo_text(ws, p: Promo) -> str:
    lines = []
    for s in p.segments:
        ep = ws.episode(s.episode)
        lines.append(f"-- Ep {s.episode} {s.start_ts}-{s.end_ts}")
        lines += [e.line() for e in ep.events if s.start - 1e-6 <= e.start < s.end - 1e-6 and e.kind != "CAMERA"]
    return "\n".join(lines)[:2500]


def _pick_for_judging(cands: list[Promo], k: int) -> list[Promo]:
    """Best k distinct moments (near-duplicate cuts are not judged twice)."""
    picked: list[Promo] = []
    for p in sorted(cands, key=lambda p: -p.scores.overall):
        if not any(is_duplicate(p, q) for q in picked):
            picked.append(p)
        if len(picked) >= k:
            break
    return picked


def register(reg: ToolRegistry) -> None:
    @reg.register("find_hook_candidates", "Strongest possible openings (first 3s) in an episode", EpisodeIn, MomentsOut)
    def find_hook_candidates(ws, inp):
        hs = hook_candidates(ws.episode(inp.episode_id), ws.analysis(inp.episode_id))
        return MomentsOut(episode=inp.episode_id, moments=[{"time": h.time, "strength": h.strength,
                                                              "event_id": h.event_id, "labels": h.labels} for h in hs])

    @reg.register("find_cliffhanger_candidates", "Strongest unresolved cut points in an episode", EpisodeIn, MomentsOut)
    def find_cliffhanger_candidates(ws, inp):
        cs = cliff_candidates(ws.episode(inp.episode_id), ws.analysis(inp.episode_id))
        return MomentsOut(episode=inp.episode_id, moments=[{"time": c.time, "strength": c.strength,
                                                              "event_id": c.event_id, "labels": c.labels} for c in cs])

    @reg.register("generate_promo_candidates", "Continuous + multi-segment candidates for an episode", EpisodeIn, GenOut)
    def generate_promo_candidates(ws, inp):
        n = inp.episode_id
        eps, ans = ws.episodes(), ws.analyses()
        out = continuous(eps[n], ans[n], eps, ans) + multi_segment(eps[n], ans[n], eps, ans)
        ws.store.save_artifact(ws.run_id, f"candidates_{n:03d}", out)
        kinds: dict[str, int] = {}
        for p in out:
            kinds[p.kind] = kinds.get(p.kind, 0) + 1
        return GenOut(episode=n, generated=len(out), kinds=kinds)

    @reg.register("generate_cross_episode_candidates", "Trailer-style promos across neighbouring episodes", Empty, GenOut)
    def generate_cross_episode_candidates(ws, _):
        out = cross_episode(ws.episodes(), ws.analyses())
        ws.store.save_artifact(ws.run_id, "candidates_cross", out)
        return GenOut(generated=len(out), kinds={"cross_episode": len(out)})

    @reg.register("calculate_promo_score", "Explainable 1-5 scores (rules, blended with LLM verdicts)", ScoreIn, ScoreOut)
    def calculate_promo_score(ws, inp):
        eps, ans = ws.episodes(), ws.analyses()
        if inp.stage == "heuristic":
            ws.promos = []
            for n in eps:
                ws.promos += [Promo.model_validate(p) for p in (ws.store.load_artifact(ws.run_id, f"candidates_{n:03d}") or [])]
            ws.promos += [Promo.model_validate(p) for p in (ws.store.load_artifact(ws.run_id, "candidates_cross") or [])]
            seen, uniq = set(), []
            for p in ws.promos:
                if p.promo_id not in seen:
                    seen.add(p.promo_id)
                    uniq.append(p)
            ws.promos = uniq
            if not ws.promos:
                raise RuntimeError("no candidates to score")
            cal = Calibrator([p.rule_hook for p in ws.promos], [p.rule_cliff for p in ws.promos])
            ws.store.save_artifact(ws.run_id, "calibration", cal.to_dict())
            for p in ws.promos:
                apply_scores(p, heuristic_scores(p, eps, ans, cal), ws.weights)
            ws.save_promos()
            return ScoreOut(scored=len(ws.promos), mean_overall=round(sum(p.scores.overall for p in ws.promos) / len(ws.promos), 3))
        # final: merge LLM verdicts saved by judge tasks
        ws.load_promos()
        verdicts: dict[str, dict] = {}
        for n in list(eps) + [0]:
            for v in ws.store.load_artifact(ws.run_id, f"judge_{n:03d}") or []:
                verdicts[v["candidate_id"]] = v
        mock = MockProvider()
        judged = 0
        cd = ws.store.load_artifact(ws.run_id, "calibration") or {}
        cal = Calibrator(cd.get("hooks"), cd.get("cliffs"))
        for p in ws.promos:
            heur = heuristic_scores(p, eps, ans, cal)
            v = verdicts.get(p.promo_id)
            if v:
                judged += 1
                apply_scores(p, heur, ws.weights, v.get("scores"), v.get("provider", "llm"))
                p.why_it_works = v.get("why_it_works") or p.why_it_works
                p.judge.verdict, p.judge.comment, p.judge.provider = v.get("verdict", ""), v.get("comment", ""), v.get("provider", "")
                p.judge.panel, p.judge.agreement = v.get("panel") or [], v.get("agreement", "")
            else:
                apply_scores(p, heur, ws.weights)
            if not p.why_it_works or not p.judge.verdict:
                mv = mock.judge(JudgeRequest(episode=p.segments[0].episode, story_so_far="", logline="", candidates=[
                    JudgeCandidate(candidate_id=p.promo_id, kind=p.kind, duration=p.duration, transcript="",
                                   hook_text=p.hook.text if p.hook else "", cliff_text=p.cliffhanger.text if p.cliffhanger else "",
                                   labels=sorted(p.labels, key=lambda k: -p.labels[k]),
                                   heuristic={k: getattr(p.scores, k) for k in ("hook", "cliffhanger", "standalone", "emotion", "coherence")})]))
                mv0 = mv.verdicts[0]
                p.why_it_works = p.why_it_works or mv0.why_it_works
                if not p.judge.verdict:
                    p.judge.verdict, p.judge.comment, p.judge.provider = mv0.verdict, mv0.comment, mock.name
        ws.save_promos()
        return ScoreOut(scored=len(ws.promos), judged=judged,
                        mean_overall=round(sum(p.scores.overall for p in ws.promos) / len(ws.promos), 3))

    @reg.register("judge_promos", "LLM judge for an episode's best candidates (0 = cross-episode)", EpisodeIn, JudgeOut)
    def judge_promos(ws, inp):
        n = inp.episode_id
        ws.load_promos()
        if n == 0:
            pool = [p for p in ws.promos if p.kind == "cross_episode"]
            k = 8
        else:
            pool = [p for p in ws.promos if p.kind != "cross_episode" and p.segments[0].episode == n]
            k = 4
        picked = _pick_for_judging(pool, k)
        if not picked:
            ws.store.save_artifact(ws.run_id, f"judge_{n:03d}", [])
            return JudgeOut(episode=n, judged=0, provider=ws.llm.name)
        ctx = ws.context()
        first = picked[0].segments[0].episode
        req = JudgeRequest(
            episode=n or first, story_so_far=ctx.story_so_far(first), logline=ctx.loglines.get(n or first, ""),
            candidates=[JudgeCandidate(
                candidate_id=p.promo_id, kind=p.kind, duration=p.duration, transcript=_promo_text(ws, p),
                hook_text=p.hook.text if p.hook else "", cliff_text=p.cliffhanger.text if p.cliffhanger else "",
                labels=sorted(p.labels, key=lambda x: -p.labels[x])[:5],
                heuristic={c: getattr(p.scores, c) for c in ("hook", "cliffhanger", "standalone", "emotion", "coherence")})
                for p in picked])
        resp = ws.llm.judge(req)
        ws.raw_dir.mkdir(parents=True, exist_ok=True)
        (ws.raw_dir / f"judge_{n:03d}.json").write_text(json.dumps(
            {"provider": resp.provider, "episode": n, "candidate_ids": [c.candidate_id for c in req.candidates],
             "raw_response": resp.raw}, indent=1))
        rows = [dict(v.model_dump(), provider=resp.provider) for v in resp.verdicts]
        ws.store.save_artifact(ws.run_id, f"judge_{n:03d}", rows)
        missing = len(picked) - len(rows)
        return JudgeOut(episode=n, judged=len(rows), provider=resp.provider, needs_review=missing > 0)
