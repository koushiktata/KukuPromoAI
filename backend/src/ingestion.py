"""Phase 1: inventory + format report for the input pack."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .parser import Episode, fmt_ts, load_show


def inventory(eps: list[Episode], folder: Path) -> dict:
    nums = [e.number for e in eps]
    expected = set(range(1, max(nums) + 1)) if nums else set()
    by_hash = Counter(e.sha1 for e in eps)
    return {
        "folder": folder.name,
        "files_found": len(eps),
        "episode_range": [min(nums), max(nums)] if nums else None,
        "missing_episodes": sorted(expected - set(nums)),
        "duplicate_episode_numbers": sorted(n for n, c in Counter(nums).items() if c > 1),
        "duplicate_file_contents": [e.file_name for e in eps if by_hash[e.sha1] > 1],
        "total_runtime": fmt_ts(sum(e.duration for e in eps)),
        "episodes": [{
            "episode": e.number, "file": e.file_name, "duration_s": round(e.duration, 2),
            "scenes": len(e.scenes), "events": len(e.events),
            "dialogue_lines": sum(1 for x in e.events if x.kind == "DIALOGUE"),
            "issues": e.issues,
        } for e in eps],
    }


def format_report(eps: list[Episode], inv: dict) -> str:
    kinds = Counter(x.kind for e in eps for x in e.events)
    speakers = Counter(x.speaker for e in eps for x in e.events if x.kind == "DIALOGUE")
    emotions = Counter(m.lower() for e in eps for x in e.events for m in x.emotions)
    durs = [e.duration for e in eps]
    gaps = overlaps = 0
    for e in eps:
        dl = [x for x in e.events if x.kind == "DIALOGUE"]
        for a, b in zip(dl, dl[1:]):
            overlaps += b.start < a.end - 0.05
    issues = [f"- Ep {e.number}: {i}" for e in eps for i in e.issues]
    return "\n".join([
        "# Screenplay format report", "",
        f"Files: **{inv['files_found']}** · episodes {inv['episode_range']} · missing: {inv['missing_episodes'] or 'none'} · "
        f"duplicate numbers: {inv['duplicate_episode_numbers'] or 'none'} · duplicate contents: {inv['duplicate_file_contents'] or 'none'}",
        f"Total runtime: {inv['total_runtime']} · episode length {fmt_ts(min(durs))}–{fmt_ts(max(durs))} (mean {sum(durs)/len(durs):.0f}s)", "",
        "## Structure",
        "- Header: `EPISODE NUMBER`, `EPISODE LOGLINE`, `CONTINUITY NOTES`, then `--- SCRIPT START ---` … `--- SCRIPT END ---`.",
        "- Scenes: `SCENE NN`, `Scene heading: INT./EXT. PLACE – TIME`, `Scene start: MM:SS.ss`, `Scene end: MM:SS.ss`.",
        "- Blocks: `**CAMERA:**`, `**ACTION:**`, `**SOUND FX:**`, or `**SPEAKER (Emotion, Emotion):**`, followed by "
        "`Start: (MM:SS.ss) | End: (MM:SS.ss)` and the text.",
        "- Timestamps are **per episode** (each episode restarts at 00:00.00), precision 0.01s. Every block has its own start and end, "
        "so clip boundaries can be taken from real events instead of being estimated.",
        f"- Overlapping dialogue lines (next line starts before previous ends): {overlaps}. CAMERA blocks overlap ACTION/dialogue by design.", "",
        "## Event counts", *[f"- {k}: {v}" for k, v in kinds.most_common()], "",
        "## Character naming",
        "Speaker names vary across episodes (e.g. `JULIANA` / `LADY JULIANA`, `CLARISSA` / `LADY IN GOLD GOWN`, "
        "`GERALD` / `THE FORMER GROOM`, `ALEXANDER` / `MYSTERIOUS BEARDED MAN` / `THE BEARDED STRANGER`). "
        "The character module resolves these to canonical names with an alias table, and the decision is recorded.",
        "", "Top speakers: " + ", ".join(f"{s} ({c})" for s, c in speakers.most_common(15)), "",
        "## Emotion tags (in dialogue headers)",
        "Dialogue headers carry the writer's emotion tags, which we use as a strong NLP signal. Top tags: "
        + ", ".join(f"{s} ({c})" for s, c in emotions.most_common(20)), "",
        "## Parser issues", *(issues or ["- none"]), "",
        "## Parser strategy",
        "Deterministic regex parser: one event per tagged block, with episode, scene, kind, speaker, emotion tags, start/end seconds "
        "and the **source line number**. Blocks without a readable timestamp are reported, never guessed. "
        "Promo cut points are only allowed on real event boundaries.",
    ])


def run_phase1(folder: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    eps = load_show(folder)
    inv = inventory(eps, folder)
    (out / "data_inventory.json").write_text(json.dumps(inv, indent=2))
    (out / "screenplay_format_report.md").write_text(format_report(eps, inv))
    return inv
