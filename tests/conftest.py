"""Test setup: synthetic screenplays (no confidential data) + isolated output/DB directories.
Environment variables are set BEFORE backend modules are imported."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="kukupromo-tests-"))
os.environ.update({
    "KUKU_DATA_DIR": str(_TMP / "scripts"), "KUKU_OUTPUT_DIR": str(_TMP / "outputs"),
    "KUKU_DB_PATH": str(_TMP / "outputs" / "test.db"), "KUKU_CHECKPOINT_DIR": str(_TMP / "outputs" / "checkpoints"),
    "LLM_PROVIDER": "mock", "LLM_SLEEP_SECONDS": "0", "KUKU_ENV_FILE": str(_TMP / "test.env"),
    "KUKU_SHOWS_DIR": str(_TMP / "shows"),
})
for _k in ("LLM_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(_k, None)          # tests never use real keys

import pytest  # noqa: E402


def ts(sec: float) -> str:
    m = int(sec // 60)
    return f"{m:02d}:{sec - m * 60:05.2f}"


def block(tag: str, start: float, end: float, text: str) -> str:
    return f"**{tag}:**\nStart: ({ts(start)}) | End: ({ts(end)})\n{text}\n"


def make_episode(n: int) -> str:
    """~75s episode with a betrayal hook, a slap, a threat and an unanswered-question cliffhanger."""
    b = [f"EPISODE NUMBER: Episode {n}",
         f"EPISODE LOGLINE: Mara is betrayed at her wedding in episode {n} and a secret heir arrives.",
         "CONTINUITY NOTES: Synthetic test episode.", "", "--- SCRIPT START ---", "", "SCENE 01",
         "Scene heading: INT. CHAPEL – DAY", "Scene start: 00:00.00", "Scene end: 01:15.00", "", "Actions and dialogue:", ""]
    t = 0.0
    lines = [
        ("CAMERA", 3.0, "Wide shot of the chapel doors opening."),
        ("MARA (Joyful)", 2.0, '"Today I marry the man I love."'),
        ("ACTION", 3.0, "Mara walks down the aisle, smiling."),
        ("GUEST (Whispering)", 2.0, '"Look at the altar."'),
        ("MARA (Shocked, Gasping)", 2.0, '"Why is he holding her hand?"'),
        ("SISTER (Gloating, Cruel)", 2.5, '"Because he is marrying me."'),
        ("ACTION", 2.5, "Mara's sister strikes her across the face with a sharp slap."),
        ("MARA (Furious, Shouting)", 2.0, '"How dare you betray me!"'),
        ("ACTION", 3.0, "A heavy wet slap as the book lands in the puddle."),
        ("GROOM (Cold)", 3.0, '"You are worthless. Get out."'),
        ("MARA (Trembling)", 3.0, '"You promised me forever."'),
        ("CAMERA", 3.0, "Close-up on Mara's tears."),
        ("FATHER (Stern)", 3.0, '"Leave this chapel or you will hang for theft."'),
        ("MARA (Defiant, Passionate)", 3.0, '"Then hang me. I will not kneel."'),
        ("ACTION", 3.0, "The doors burst open. A scarred stranger enters."),
        ("STRANGER (Commanding)", 3.0, '"Unhand her."'),
        ("SISTER (Afraid)", 2.0, '"Who are you?"'),
        ("ACTION", 4.0, "The stranger kneels before Mara, ignoring everyone."),
        ("STRANGER (Low)", 3.0, '"I am the rightful duke, and I came for you."'),
        ("MARA (Stunned)", 2.0, '"The duke? He was presumed dead..."'),
        ("CAMERA", 3.0, "Push in on the stranger's scar."),
        ("FATHER (Shocked)", 3.0, '"Impossible. Guards, seize him!"'),
        ("ACTION", 3.0, "Guards draw a sword and close in."),
        ("MARA (Desperate)", 3.0, '"Will you fight them all?"'),
        ("SOUND FX", 3.0, "An ominous string sting swells into a cliffhanger."),
        ("CAMERA", 2.0, "Cut to black."),
    ]
    for tag, dur, text in lines:
        b.append(block(tag, t, t + dur, text))
        t = round(t + dur + 0.5, 2)
    b[8] = f"Scene end: {ts(t)}"
    b.append("--- SCRIPT END ---")
    return "\n".join(b)


@pytest.fixture(scope="session")
def data_dir() -> Path:
    d = Path(os.environ["KUKU_DATA_DIR"])
    d.mkdir(parents=True, exist_ok=True)
    for n in (1, 2, 3):
        (d / f"episode-{n:03d}-Episode {9000 + n}.txt").write_text(make_episode(n))
    return d


@pytest.fixture(scope="session")
def episodes(data_dir):
    from backend.src.parser import load_show
    return load_show(data_dir)


@pytest.fixture(scope="session")
def analyses(episodes):
    from backend.src.nlp_analysis import analyse_episode
    return {e.number: analyse_episode(e) for e in episodes}


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
