import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.sync_check import Pulse, compare


def _mk(codes, offset=0.0, jitter=0.0, seed=3):
    rng = random.Random(seed)
    return [Pulse(c, i * 1.0 + offset + (rng.gauss(0, jitter) if jitter else 0.0))
            for i, c in enumerate(codes)]


def test_clean_calibration_passes_and_recovers_the_known_offset():
    codes = [101, 102, 103, 104, 105]
    rep = compare(codes, _mk(codes), _mk(codes, offset=0.030, jitter=0.005), session="t")
    assert rep.verdict == "PASS"
    assert abs((rep.offset_ms or 0) - 30) < 6
    assert (rep.jitter_sd_ms or 0) < 40


def test_missing_pulse_fails_primarily():
    codes = [101, 102, 103, 104, 105]
    rep = compare(codes, _mk(codes), _mk(codes)[:-1], session="t")
    assert rep.verdict == "FAIL"
    assert 105 in rep.missing_codes
    assert any("丢失" in r or "不一致" in r for r in rep.reasons)


def test_large_jitter_fails():
    codes = [101, 102, 103, 104, 105, 106, 107, 108]
    rep = compare(codes, _mk(codes), _mk(codes, jitter=0.060, seed=11), session="t")
    assert rep.verdict == "FAIL"
    assert any("jitter" in r for r in rep.reasons)
