import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod
from bplus.paradigms import REGISTRY
from bplus.realtime import NullPresenter, NullWindow, SimulatedLine, TriggerPulse, run_events
from bplus.timing import PulsePolicy, check_events, check_event_spacing

NAMES = ("rest", "mmn", "vft", "nback", "emotion", "recovery")


class FakeClock:
    """可控时钟：每次读取前进 5 ms。"""

    def __init__(self, start: float = 0.0, step: float = 0.005) -> None:
        self.t = start
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def policy() -> PulsePolicy:
    return PulsePolicy.from_config(cfg_mod.load_yaml("sync.yaml"))


def test_frozen_policy_is_internally_consistent():
    p = policy()
    assert p.problems() == [], p.problems()
    # 核心工程规则：不锁存（或未确认锁存）时，脉宽必须大于 fNIRS 采样周期
    assert p.latching == "unknown"
    assert p.width_ms > p.fnirs_sampling_interval_ms
    assert p.max_event_quantisation_ms() == 75.0


def test_a_too_short_pulse_is_rejected():
    bad = PulsePolicy(width_ms=50, min_gap_ms=500, latching="unknown", fnirs_sampling_interval_ms=75)
    problems = bad.problems()
    assert problems and "漏抓" in problems[0]
    short_if_latched = PulsePolicy(width_ms=50, min_gap_ms=500, latching="yes", fnirs_sampling_interval_ms=75)
    assert short_if_latched.problems() == []


@pytest.mark.parametrize("name", NAMES)
def test_every_paradigm_respects_pulse_spacing(name):
    cfg = cfg_mod.paradigm_config(name)
    events = REGISTRY[name](cfg).events()
    issues = check_events(events, policy())
    assert issues == [], f"{name}: {issues[:3]}"


def test_event_spacing_flags_overlapping_pulses():
    issues = check_event_spacing([0, 60, 900], policy())
    assert any("重叠" in i for i in issues)


def test_pulse_state_machine_holds_for_the_configured_width():
    clock = FakeClock(step=0.005)
    line = SimulatedLine(clock=clock)
    pulse = TriggerPulse(line=line, policy=policy(), clock=clock)

    pulse.arm(101)
    assert line.edges[-1][1] == "high"
    for _ in range(5):                      # ~25 ms，仍应保持高电平
        pulse.poll()
    assert line.edges[-1][1] == "high"

    for _ in range(30):                     # 继续推进到 >100 ms
        pulse.poll()
    assert line.edges[-1][1] == "low"
    assert line.codes == [101]
    assert pulse.events[0][1] == 101


def test_run_events_fires_exactly_one_trigger_per_event():
    cfg = cfg_mod.paradigm_config("nback")
    events = REGISTRY["nback"](cfg).events()
    window = NullWindow(speed=0.0)                  # 虚拟帧时钟
    line = SimulatedLine(clock=window.now)
    pulse = TriggerPulse(line=line, policy=policy(), clock=window.now)
    seen = []

    report = run_events(events, window=window, pulse=pulse,
                        presenter=NullPresenter(on_draw=seen.append), paradigm="nback")

    assert report.n_events == len(events)
    assert seen == sorted(events, key=lambda e: e.onset)
    assert line.codes == [int(e.code) for e in sorted(events, key=lambda e: e.onset)]
    assert len(line.codes) == len(set((round(e.onset, 6), int(e.code)) for e in events))

    # 虚拟帧时钟下，脉宽应当落在目标值附近（一帧 = 16.7 ms）
    widths_ms = [w * 1000 for w in line.pulse_widths()]
    assert widths_ms, "没有记录到任何脉冲"
    target = policy().width_ms
    assert all(abs(w - target) <= 20 for w in widths_ms), (widths_ms[:5], target)
