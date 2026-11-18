"""Screenplay + character tools."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..harness.tool_registry import ToolRegistry
from ..src.character_analysis import character_history
from ..src.nlp_analysis import search_moments, sentiment_backend


class Empty(BaseModel):
    pass


class EpisodeIn(BaseModel):
    episode_id: int = Field(ge=0)


class FilesOut(BaseModel):
    count: int
    episodes: list[int]
    missing: list[int]


class ParseOut(BaseModel):
    episode: int
    duration: float
    scenes: int
    events: int
    issues: list[str]
    needs_review: bool = False


class AnalyseOut(BaseModel):
    episode: int
    labels: dict[str, int]
    peak_times: list[float]
    sentiment_backend: str


class ContextOut(BaseModel):
    episode: int
    logline: str
    story_so_far: str
    main_cast: list[str]


class StoryOut(BaseModel):
    characters: int
    relationships: int
    main_cast: list[str]


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=80)
    limit: int = Field(default=10, ge=1, le=50)


class SearchOut(BaseModel):
    results: list[dict]


class CharIn(BaseModel):
    character_name: str = Field(min_length=1, max_length=60)


class CharOut(BaseModel):
    found: bool
    data: dict


def register(reg: ToolRegistry) -> None:
    @reg.register("list_episode_files", "List screenplay files and detect gaps", Empty, FilesOut)
    def list_episode_files(ws, _):
        files = ws.scan_files()
        if not files:
            raise RuntimeError(f"no episode files found in {ws.data_dir.name}")
        nums = sorted(files)
        ws.episode_ids = ws.episode_ids or nums
        missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
        return FilesOut(count=len(nums), episodes=nums, missing=missing)

    @reg.register("parse_episode", "Parse one screenplay into timed events", EpisodeIn, ParseOut)
    def parse_episode(ws, inp):
        ep = ws.episode(inp.episode_id)
        return ParseOut(episode=ep.number, duration=ep.duration, scenes=len(ep.scenes), events=len(ep.events),
                        issues=ep.issues, needs_review=bool(ep.issues))

    @reg.register("analyse_episode", "NLP: sentiment, emotion, dramatic events", EpisodeIn, AnalyseOut)
    def analyse_episode_tool(ws, inp):
        an = ws.analysis(inp.episode_id)
        return AnalyseOut(episode=an.episode, labels=an.label_counts, peak_times=[p["time"] for p in an.peak_moments],
                          sentiment_backend=sentiment_backend())

    @reg.register("get_episode_context", "Logline + story so far + main cast for an episode", EpisodeIn, ContextOut)
    def get_episode_context(ws, inp):
        ctx = ws.context()
        return ContextOut(episode=inp.episode_id, logline=ctx.loglines.get(inp.episode_id, ""),
                          story_so_far=ctx.story_so_far(inp.episode_id), main_cast=ctx.main_cast())

    @reg.register("build_story_context", "Characters, aliases and relationships across episodes", Empty, StoryOut)
    def build_story_context(ws, _):
        ctx = ws.context()
        ws.store.save_artifact(ws.run_id, "story_context", ctx)
        return StoryOut(characters=len(ctx.characters), relationships=len(ctx.relationships), main_cast=ctx.main_cast())

    @reg.register("search_dramatic_moments", "Search events by dramatic label or text", SearchIn, SearchOut)
    def search_dramatic_moments(ws, inp):
        return SearchOut(results=search_moments(list(ws.episodes().values()), ws.analyses(), inp.query, inp.limit))

    @reg.register("get_character_history", "A character's aliases, episodes, emotions, relationships", CharIn, CharOut)
    def get_character_history(ws, inp):
        d = character_history(ws.context(), inp.character_name)
        return CharOut(found=d["found"], data=d)
