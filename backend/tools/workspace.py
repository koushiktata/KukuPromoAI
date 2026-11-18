"""Per-run working memory shared by the tools. Deterministic data (parsed screenplays, NLP)
is rebuilt on demand; expensive or stateful data (candidates, LLM verdicts, promos) is
checkpointed so a resumed run never repeats LLM calls."""
from __future__ import annotations

from pathlib import Path

from ..harness.checkpoint import CheckpointStore
from ..llm.base import LLMProvider
from ..src.character_analysis import StoryContext, build_context
from ..src.models import ContentFlag, Promo, Secret
from ..src.nlp_analysis import EpisodeAnalysis, analyse_episode
from ..src.parser import Episode, parse_file


class Workspace:
    def __init__(self, run_id: str, data_dir: Path, output_dir: Path, store: CheckpointStore, llm: LLMProvider,
                 weights: dict[str, float], db=None, episode_ids: list[int] | None = None):
        self.run_id, self.data_dir, self.output_dir = run_id, Path(data_dir), Path(output_dir)
        self.store, self.llm, self.weights, self.db = store, llm, weights, db
        self.episode_ids = episode_ids
        self.files: dict[int, Path] = {}
        self._episodes: dict[int, Episode] = {}
        self._analyses: dict[int, EpisodeAnalysis] = {}
        self._ctx: StoryContext | None = None
        self.promos: list[Promo] = []          # all candidates (scored / validated in place)
        self.ranked: list[Promo] = []          # group heads after ranking
        self.secrets: list[Secret] = []
        self.flags: list[ContentFlag] = []
        self.raw_dir = self.output_dir / "raw_model_outputs" / run_id

    # ----- screenplay data -----
    def episode(self, n: int) -> Episode:
        if n not in self._episodes:
            if n not in self.files:
                self.scan_files()
            if n not in self.files:
                raise KeyError(f"episode {n} not found in {self.data_dir.name}")
            self._episodes[n] = parse_file(self.files[n])
        return self._episodes[n]

    def scan_files(self) -> dict[int, Path]:
        import re
        self.files = {}
        for p in sorted(self.data_dir.glob("*.txt")):
            m = re.search(r"episode[-_ ]0*(\d+)", p.name, re.I)
            if m:
                self.files[int(m.group(1))] = p
        return self.files

    def episodes(self) -> dict[int, Episode]:
        ids = self.episode_ids or sorted(self.scan_files())
        return {n: self.episode(n) for n in ids}

    def analysis(self, n: int) -> EpisodeAnalysis:
        if n not in self._analyses:
            self._analyses[n] = analyse_episode(self.episode(n))
        return self._analyses[n]

    def analyses(self) -> dict[int, EpisodeAnalysis]:
        return {n: self.analysis(n) for n in self.episodes()}

    def context(self) -> StoryContext:
        if self._ctx is None:
            eps = self.episodes()
            self._ctx = build_context(list(eps.values()), self.analyses())
        return self._ctx

    # ----- checkpointed state -----
    def save_promos(self, key: str = "promos") -> None:
        self.store.save_artifact(self.run_id, key, self.promos)

    def load_promos(self, key: str = "promos") -> list[Promo]:
        if not self.promos:
            data = self.store.load_artifact(self.run_id, key)
            if data:
                self.promos = [Promo.model_validate(p) for p in data]
        return self.promos

    def load_secrets_flags(self) -> None:
        if not self.secrets:
            self.secrets = [Secret.model_validate(s) for s in (self.store.load_artifact(self.run_id, "secrets") or [])]
        if not self.flags:
            self.flags = [ContentFlag.model_validate(f) for f in (self.store.load_artifact(self.run_id, "flags") or [])]

    def load_ranked(self) -> list[Promo]:
        if not self.ranked:
            data = self.store.load_artifact(self.run_id, "ranked")
            if data:
                self.ranked = [Promo.model_validate(p) for p in data]
        return self.ranked
