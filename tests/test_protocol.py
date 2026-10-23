import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod
from bplus.protocol import build_session

NAMES = ("rest", "mmn", "vft", "nback", "emotion", "recovery")


def _timeline():
    protocol = cfg_mod.protocol_config()
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    return build_session(protocol, paradigms, strict=True)


def test_session_is_70_minutes_and_contiguous():
    tl = _timeline()
    assert tl.total_duration_s == pytest.approx(4200.0, abs=1e-6)
    assert [p.name for p in tl.phases][:3] == ["consent_questionnaires", "setup_qc", "rest_baseline"]


def test_computer_paradigm_phase_fits_the_20_minute_budget():
    tl = _timeline()
    phase = next(p for p in tl.phases if p.name == "computer_paradigms")
    last = max(e.onset_s for e in tl.events_in("computer_paradigms"))
    assert last <= phase.end_s
    assert phase.duration_s == 1200


def test_every_paradigm_emits_start_and_end_markers():
    tl = _timeline()
    pairs = {"rest": ("REST_START", "REST_END"), "mmn": ("MMN_START", "MMN_END"),
             "vft": ("VFT_START", "VFT_END"), "nback": ("NBACK_START", "NBACK_END"),
             "emotion": ("EMOTION_START", "EMOTION_END"), "recovery": ("RECOVERY_START", "RECOVERY_END")}
    for paradigm, (start, end) in pairs.items():
        names = [e.name for e in tl.events if e.meta.get("paradigm") == paradigm]
        assert start in names and end in names, paradigm


def test_events_are_unique_and_inside_the_session():
    tl = _timeline()
    keys = {(round(e.onset_s, 6), int(e.code)) for e in tl.events}
    assert len(keys) == len(tl.events)
    assert all(0 <= e.onset_s <= tl.total_duration_s for e in tl.events)


def test_strict_mode_rejects_an_overflowing_paradigm_budget():
    protocol = cfg_mod.protocol_config()
    protocol = {**protocol, "phases": [dict(p) for p in protocol["phases"]]}
    for phase in protocol["phases"]:
        if phase["name"] == "computer_paradigms":
            phase["duration_s"] = 60          # far too short
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    protocol["total_duration_s"] = sum(p["duration_s"] for p in protocol["phases"])
    with pytest.raises(ValueError, match="overflow"):
        build_session(protocol, paradigms, strict=True)
