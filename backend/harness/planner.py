"""The orchestrator's plan: a fixed, inspectable DAG of tasks. Agents cannot add tasks,
so there is no way to recurse or loop."""
from __future__ import annotations

from .state import Task

OBJECTIVE = ("Find ranked 20-60s promos (hook in first 3s, unresolved cliffhanger, standalone) with exact, "
             "validated screenplay timestamps; flag spoilers and sensitive content for human review.")


def build_plan(episode_ids: list[int], max_retries: int = 2) -> list[Task]:
    tasks: list[Task] = []

    def add(tid, stage, agent, tool, args=None, deps=None, critical=True):
        tasks.append(Task(task_id=tid, stage=stage, agent=agent, tool=tool, args=args or {},
                          depends_on=deps or [], max_retries=max_retries, critical=critical))

    add("inventory", "1 · Ingest", "screenplay_agent", "list_episode_files")
    parse_ids, analyse_ids = [], []
    for n in episode_ids:
        add(f"parse_{n:03d}", "1 · Ingest", "screenplay_agent", "parse_episode", {"episode_id": n}, ["inventory"],
            critical=False)
        parse_ids.append(f"parse_{n:03d}")
    for n in episode_ids:
        add(f"analyse_{n:03d}", "2 · Understand", "screenplay_agent", "analyse_episode", {"episode_id": n},
            [f"parse_{n:03d}"], critical=False)
        analyse_ids.append(f"analyse_{n:03d}")
    add("story_context", "2 · Understand", "screenplay_agent", "build_story_context", deps=analyse_ids)
    add("secrets", "2 · Understand", "quality_reviewer_agent", "detect_secrets", deps=["story_context"])
    add("content_flags", "2 · Understand", "quality_reviewer_agent", "detect_content_flags", deps=parse_ids)
    gen_ids = []
    for n in episode_ids:
        add(f"discover_{n:03d}", "3 · Discover", "promo_discovery_agent", "generate_promo_candidates",
            {"episode_id": n}, ["story_context"], critical=False)
        gen_ids.append(f"discover_{n:03d}")
    add("discover_cross", "3 · Discover", "promo_discovery_agent", "generate_cross_episode_candidates",
        deps=gen_ids, critical=False)
    add("prescore", "4 · Score", "scoring_agent", "calculate_promo_score", {"stage": "heuristic"}, ["discover_cross"])
    judge_ids = []
    for n in episode_ids:
        add(f"judge_{n:03d}", "4 · Score", "promo_discovery_agent", "judge_promos", {"episode_id": n}, ["prescore"],
            critical=False)
        judge_ids.append(f"judge_{n:03d}")
    add("judge_cross", "4 · Score", "promo_discovery_agent", "judge_promos", {"episode_id": 0}, ["prescore"],
        critical=False)
    add("final_score", "4 · Score", "scoring_agent", "calculate_promo_score", {"stage": "final"},
        judge_ids + ["judge_cross"])
    add("validate", "5 · Validate", "validation_agent", "validate_promo", {"all": True}, ["final_score"])
    add("categorize", "5 · Validate", "quality_reviewer_agent", "classify_audience", deps=["validate", "secrets",
                                                                                           "content_flags"])
    add("rank", "6 · Rank", "scoring_agent", "rank_promos", deps=["categorize"])
    add("quality_review", "6 · Rank", "quality_reviewer_agent", "review_quality", deps=["rank"])
    add("save", "7 · Save", "orchestrator", "save_results", deps=["quality_review"])
    return tasks
