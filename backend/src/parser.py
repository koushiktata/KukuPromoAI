"""Deterministic screenplay parser (regex only, no AI).

Format observed in the input pack (see outputs/screenplay_format_report.md):

    EPISODE NUMBER: Episode 1
    EPISODE LOGLINE: ...
    CONTINUITY NOTES: ...
    --- SCRIPT START ---
    SCENE 01
    Scene heading: INT. CATHEDRAL – DAY
    Scene start: 00:00.00
    Scene end: 02:18.00
    **CAMERA:** | **ACTION:** | **SOUND FX:** | **SPEAKER NAME (Emotion, Emotion):**
    Start: (00:00.00) | End: (00:04.80)
    <one or more lines of text>
    --- SCRIPT END ---

Every event keeps the source line number so any recommendation can be traced back to the file.
Anything the parser cannot read is recorded as an issue instead of being guessed.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, Field

TAG_RE = re.compile(r"^\*\*(?P<tag>[^*]+?):\*\*\s*$")
TIME_RE = re.compile(r"Start:\s*\((?P<s>\d{1,2}:\d{2}(?:\.\d+)?)\)\s*\|\s*End:\s*\((?P<e>\d{1,2}:\d{2}(?:\.\d+)?)\)")
SCENE_TIME_RE = re.compile(r"^Scene (?P<which>start|end):\s*(?P<t>\d{1,2}:\d{2}(?:\.\d+)?)")
SPEAKER_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<emo>[^)]*)\)\s*$")
FILE_EP_RE = re.compile(r"episode[-_ ]0*(\d+)", re.I)
HEADER_EP_RE = re.compile(r"EPISODE NUMBER:\s*Episode\s*(\d+)", re.I)


def to_seconds(ts: str) -> float:
    """'01:23.45' -> 83.45. Raises ValueError on bad input."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2}(?:\.\d+)?)\s*", ts)
    if not m:
        raise ValueError(f"bad timestamp {ts!r}")
    sec = float(m.group(2))
    if sec >= 60:
        raise ValueError(f"seconds out of range in {ts!r}")
    return int(m.group(1)) * 60 + sec


def fmt_ts(sec: float) -> str:
    m = int(sec // 60)
    return f"{m:02d}:{sec - m * 60:05.2f}"


class Event(BaseModel):
    event_id: str
    episode: int
    scene_id: str
    kind: str                     # CAMERA | ACTION | SFX | DIALOGUE
    start: float
    end: float
    text: str
    speaker: str = ""
    emotions: list[str] = Field(default_factory=list)
    source_line: int              # 1-based line of the tag in the source file

    @property
    def duration(self) -> float:
        return self.end - self.start

    def label(self) -> str:
        if self.kind == "DIALOGUE":
            emo = f" ({', '.join(self.emotions)})" if self.emotions else ""
            return f"{self.speaker}{emo}"
        return self.kind

    def line(self) -> str:
        return f"[{fmt_ts(self.start)}-{fmt_ts(self.end)}] {self.label()}: {self.text}"


class Scene(BaseModel):
    scene_id: str
    heading: str = ""
    start: float | None = None
    end: float | None = None
    source_line: int = 0


class Episode(BaseModel):
    number: int
    file_name: str
    sha1: str
    logline: str = ""
    continuity: str = ""
    duration: float = 0.0
    scenes: list[Scene] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

    def events_between(self, a: float, b: float) -> list[Event]:
        return [e for e in self.events if e.start >= a - 1e-6 and e.start < b - 1e-6]

    def boundaries(self) -> tuple[list[float], list[float]]:
        """Valid cut points: starts and ends of real events."""
        starts = sorted({0.0} | {e.start for e in self.events})
        ends = sorted({e.end for e in self.events} | {self.duration})
        return starts, ends


def parse_text(text: str, file_name: str = "<memory>") -> Episode:
    lines = text.splitlines()
    head = "\n".join(lines[:10])
    hm, fm = HEADER_EP_RE.search(head), FILE_EP_RE.search(file_name)
    issues: list[str] = []
    if hm and fm and int(hm.group(1)) != int(fm.group(1)):
        issues.append(f"episode number mismatch: file says {fm.group(1)}, header says {hm.group(1)}")
    number = int(hm.group(1)) if hm else int(fm.group(1)) if fm else 0
    if not number:
        issues.append("episode number not found")
    ep = Episode(number=number, file_name=file_name, sha1=hashlib.sha1(text.encode()).hexdigest())

    scene: Scene | None = None
    cur: dict | None = None
    counter = 0

    def flush() -> None:
        nonlocal cur, counter
        if cur is None:
            return
        if cur["start"] is None:
            issues.append(f"line {cur['line']}: {cur['kind']} block has no timestamp - skipped")
        else:
            counter += 1
            if cur["end"] < cur["start"]:
                issues.append(f"line {cur['line']}: end before start - skipped")
            else:
                ep.events.append(Event(
                    event_id=f"E{number:03d}-{counter:04d}", episode=number,
                    scene_id=scene.scene_id if scene else "SCENE ?", kind=cur["kind"],
                    start=cur["start"], end=cur["end"], text=" ".join(cur["text"]).strip(),
                    speaker=cur.get("speaker", ""), emotions=cur.get("emotions", []), source_line=cur["line"]))
        cur = None

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("EPISODE LOGLINE:"):
            ep.logline = line.split(":", 1)[1].strip()
            continue
        if line.startswith("CONTINUITY NOTES:"):
            ep.continuity = line.split(":", 1)[1].strip()
            continue
        if re.match(r"^SCENE\s+\w+", line):
            flush()
            scene = Scene(scene_id=line, source_line=i)
            ep.scenes.append(scene)
            continue
        if line.startswith("Scene heading:") and scene:
            scene.heading = line.split(":", 1)[1].strip()
            continue
        sm = SCENE_TIME_RE.match(line)
        if sm and scene:
            try:
                setattr(scene, sm.group("which"), to_seconds(sm.group("t")))
            except ValueError as e:
                issues.append(f"line {i}: {e}")
            continue
        m = TAG_RE.match(line)
        if m:
            flush()
            tag = m.group("tag").strip()
            if tag in ("CAMERA", "ACTION"):
                cur = {"kind": tag}
            elif tag.upper().startswith("SOUND"):
                cur = {"kind": "SFX"}
            else:
                spm = SPEAKER_RE.match(tag)
                cur = {"kind": "DIALOGUE", "speaker": (spm.group("name") if spm else tag).strip().upper(),
                       "emotions": [x.strip() for x in spm.group("emo").split(",") if x.strip()] if spm else []}
            cur.update(start=None, end=None, text=[], line=i)
            continue
        if cur is None:
            continue
        t = TIME_RE.search(line)
        if t and cur["start"] is None:
            try:
                cur["start"], cur["end"] = to_seconds(t.group("s")), to_seconds(t.group("e"))
            except ValueError as e:
                issues.append(f"line {i}: {e}")
        elif line and not line.startswith("---"):
            cur["text"].append(line.strip('"').strip("“”"))
    flush()

    ep.events.sort(key=lambda e: (e.start, e.end, e.source_line))
    scene_ends = [s.end for s in ep.scenes if s.end is not None]
    ep.duration = max(scene_ends + [e.end for e in ep.events] + [0.0])
    if not ep.events:
        issues.append("no timed events found")
    if "--- SCRIPT END ---" not in text:
        issues.append("missing '--- SCRIPT END ---' marker (file may be truncated)")
    ep.issues = issues
    return ep


def parse_file(path: str | Path) -> Episode:
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8", errors="replace"), path.name)


def load_show(folder: str | Path) -> list[Episode]:
    eps = [parse_file(p) for p in sorted(Path(folder).glob("*.txt"))]
    return sorted(eps, key=lambda e: e.number)
