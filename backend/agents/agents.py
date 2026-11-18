"""The five specialised agents. They are logical roles over the same tool registry, not
independent LLM loops: only the Promo Discovery agent's judge step calls an LLM, once per episode."""
from __future__ import annotations

from ..harness.state import Task
from ..harness.tracing import Tracer
from .base import BaseAgent


class ScreenplayAgent(BaseAgent):
    name = "screenplay_agent"
    role = "Parse scenes and dialogue, identify characters, detect dramatic events, keep cross-episode context"
    allowed_tools = ("list_episode_files", "parse_episode", "analyse_episode", "build_story_context",
                     "get_episode_context", "get_character_history", "search_dramatic_moments")


class PromoDiscoveryAgent(BaseAgent):
    name = "promo_discovery_agent"
    role = "Find hooks and cliffhangers, build continuous / multi-segment / cross-episode promos, get LLM verdicts"
    allowed_tools = ("find_hook_candidates", "find_cliffhanger_candidates", "generate_promo_candidates",
                     "generate_cross_episode_candidates", "get_episode_context", "judge_promos")

    def handle(self, task: Task, ws, tracer: Tracer) -> dict:
        if task.tool == "generate_promo_candidates":
            n = task.args["episode_id"]
            hooks = self.call_tool("find_hook_candidates", {"episode_id": n}, ws, tracer, task.task_id)
            cliffs = self.call_tool("find_cliffhanger_candidates", {"episode_id": n}, ws, tracer, task.task_id)
            out = self.call_tool(task.tool, task.args, ws, tracer, task.task_id)
            out.update(hooks=len(hooks["moments"]), cliffs=len(cliffs["moments"]))
            if not hooks["moments"] or not out["generated"]:
                out["needs_review"] = True          # nothing promotable found: a human should look
            return out
        if task.tool == "judge_promos" and task.args.get("episode_id"):
            self.call_tool("get_episode_context", task.args, ws, tracer, task.task_id)
        return self.call_tool(task.tool, task.args, ws, tracer, task.task_id)


class ValidationAgent(BaseAgent):
    name = "validation_agent"
    role = "Verify timestamps, episodes, durations, segment order and hook timing; reject unsupported promos"
    allowed_tools = ("validate_promo",)


class ScoringAgent(BaseAgent):
    name = "scoring_agent"
    role = "Score, explain, de-duplicate and rank promos"
    allowed_tools = ("calculate_promo_score", "rank_promos")


class QualityReviewerAgent(BaseAgent):
    name = "quality_reviewer_agent"
    role = "Spot weak hooks/cliffhangers, missing context, spoilers and sensitive content; escalate to humans"
    allowed_tools = ("detect_secrets", "detect_content_flags", "classify_audience", "review_quality")


class OutputAgent(BaseAgent):
    name = "orchestrator"
    role = "Persist results"
    allowed_tools = ("save_results",)


def build_agents(registry) -> dict[str, BaseAgent]:
    return {a.name: a(registry) for a in (ScreenplayAgent, PromoDiscoveryAgent, ValidationAgent, ScoringAgent,
                                          QualityReviewerAgent, OutputAgent)}
