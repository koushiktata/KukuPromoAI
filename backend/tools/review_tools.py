"""Validation, ranking, spoiler/safety review and quality-review tools."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import settings
from ..harness.tool_registry import ToolRegistry
from ..src.content_flags import detect_flags, flags_for_promo
from ..src.models import ValidationStatus
from ..src.ranking import rank
from ..src.spoiler_analysis import categorize, find_secrets
from ..src.validation import validate_promo
from .screenplay_tools import Empty


class ValidateIn(BaseModel):
    all: bool = True
    promo_id: str = ""


class ValidateOut(BaseModel):
    checked: int
    valid: int
    invalid: int
    needs_review_count: int          # NOT "needs_review": that key means "escalate this task" to the executor


class CountOut(BaseModel):
    count: int
    by_type: dict[str, int] = Field(default_factory=dict)


class AudienceOut(BaseModel):
    new_viewer: int
    retarget: int
    neither: int


class RankOut(BaseModel):
    groups: int
    ranked: int
    invalid: int
    alternatives: int


class QualityOut(BaseModel):
    reviewed: int
    flagged_for_human: int
    notes: dict[str, int]


def quality_notes(p, flags_by_id) -> list[str]:
    notes = []
    s = p.scores
    if s.hook < 3:
        notes.append("weak hook")
    if s.cliffhanger < 3:
        notes.append("weak cliffhanger")
    if s.standalone < 3:
        notes.append("missing context for new viewers")
    if p.kind != "continuous" and s.coherence < 3.5:
        notes.append("stitched segments may feel incoherent")
    if p.hook and p.hook.kind == "CAMERA":
        notes.append("hook is visual-only: check the footage")
    if p.judge.verdict.lower().startswith("skip"):
        notes.append("judge says skip")
    if p.category.spoiler_secret_ids:
        notes.append("contains possible spoilers")
    high = [flags_by_id[f] for f in p.content_flag_ids if f in flags_by_id and flags_by_id[f].severity == "high"]
    if high:
        notes.append("high-severity content flag: " + ", ".join(sorted({f.flag_type for f in high})))
    if p.judge.agreement == "low":
        notes.append("LLM judges disagree: " + ", ".join(
            f"{m['model'].split(':')[0]} {m['overall']}" for m in p.judge.panel if m.get("overall") is not None))
    if "blended" in s.source:
        notes.append(f"scored by {s.source}")
    return notes


def register(reg: ToolRegistry) -> None:
    @reg.register("validate_promo", "Deterministic timestamp/duration/hook/cliffhanger checks", ValidateIn, ValidateOut)
    def validate_tool(ws, inp):
        ws.load_promos()
        eps = ws.episodes()
        targets = ws.promos if inp.all else [p for p in ws.promos if p.promo_id == inp.promo_id]
        if not targets:
            raise RuntimeError("nothing to validate")
        for p in targets:
            p.validation = validate_promo(p, eps, min_s=settings.promo_min_s, max_s=settings.promo_max_s,
                                          hook_window=settings.hook_window_s)
        ws.save_promos()
        st = [p.validation.status for p in targets]
        return ValidateOut(checked=len(st), valid=st.count(ValidationStatus.VALID),
                           invalid=st.count(ValidationStatus.INVALID),
                           needs_review_count=st.count(ValidationStatus.NEEDS_REVIEW))

    @reg.register("detect_secrets", "AI-generated list of show secrets with screenplay evidence", Empty, CountOut)
    def detect_secrets(ws, _):
        ws.secrets = find_secrets(list(ws.episodes().values()))
        ws.store.save_artifact(ws.run_id, "secrets", ws.secrets)
        by: dict[str, int] = {}
        for s in ws.secrets:
            by[s.severity] = by.get(s.severity, 0) + 1
        return CountOut(count=len(ws.secrets), by_type=by)

    @reg.register("detect_content_flags", "Content-review signals (violence, sexual, threats...)", Empty, CountOut)
    def detect_content_flags(ws, _):
        ws.flags = detect_flags(list(ws.episodes().values()))
        ws.store.save_artifact(ws.run_id, "flags", ws.flags)
        by: dict[str, int] = {}
        for f in ws.flags:
            by[f.flag_type] = by.get(f.flag_type, 0) + 1
        return CountOut(count=len(ws.flags), by_type=by)

    @reg.register("classify_audience", "New-viewer vs re-targeting/spoiler categories", Empty, AudienceOut)
    def classify_audience(ws, _):
        ws.load_promos()
        ws.load_secrets_flags()
        eps = ws.episodes()
        for p in ws.promos:
            p.category = categorize(p, eps, ws.secrets)
            p.content_flag_ids = flags_for_promo(p, ws.flags)
        ws.save_promos()
        nv = sum(p.category.new_viewer for p in ws.promos)
        rt = sum(p.category.retarget for p in ws.promos)
        neither = sum(not p.category.new_viewer and not p.category.retarget for p in ws.promos)
        return AudienceOut(new_viewer=nv, retarget=rt, neither=neither)

    @reg.register("rank_promos", "Duplicate control, alternative cuts, ranking and posting priority", Empty, RankOut)
    def rank_promos(ws, _):
        ws.load_promos()
        ws.ranked = rank([p.model_copy(deep=True) for p in ws.promos])
        ws.store.save_artifact(ws.run_id, "ranked", ws.ranked)
        return RankOut(groups=len(ws.ranked), ranked=sum(1 for p in ws.ranked if p.rank),
                       invalid=sum(1 for p in ws.ranked if p.validation.status == ValidationStatus.INVALID),
                       alternatives=sum(len(p.alternatives) for p in ws.ranked))

    @reg.register("review_quality", "Weak hooks/cliffhangers, missing context, escalate to humans", Empty, QualityOut)
    def review_quality(ws, _):
        ws.load_ranked()
        ws.load_secrets_flags()
        fmap = {f.flag_id: f for f in ws.flags}
        counts: dict[str, int] = {}
        flagged = 0
        for p in ws.ranked:
            p.quality_notes = quality_notes(p, fmap)
            p.needs_human_review = (p.validation.status != ValidationStatus.VALID
                                    or any(n.startswith(("weak", "missing", "judge says", "high-severity", "stitched",
                                                         "LLM judges disagree"))
                                           for n in p.quality_notes))
            flagged += p.needs_human_review
            for n in p.quality_notes:
                key = n.split(":")[0]
                counts[key] = counts.get(key, 0) + 1
        ws.store.save_artifact(ws.run_id, "ranked", ws.ranked)
        return QualityOut(reviewed=len(ws.ranked), flagged_for_human=flagged, notes=counts)
