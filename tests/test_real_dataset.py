"""Integration check on the real input pack - skipped when the confidential scripts are not present."""
from pathlib import Path

import pytest

REAL = Path(__file__).resolve().parents[1] / "data" / "scripts"
pytestmark = pytest.mark.skipif(len(list(REAL.glob("*.txt"))) < 50, reason="real input pack not available")


def test_all_50_episodes_parse_cleanly():
    from backend.src.parser import load_show
    eps = load_show(REAL)
    assert [e.number for e in eps] == list(range(1, 51))
    assert all(not e.issues for e in eps)
    assert sum(len(e.events) for e in eps) > 3000
