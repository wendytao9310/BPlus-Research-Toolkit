"""帧同步呈现后端（PsychoPy）与无头仿真后端（DEMO/测试）。

设计目标（MASTER COMMAND §18、§57-59）：
  * 触发在 `win.callOnFlip()` 里拉高 —— 呈现与打标在同一帧物理对齐；
  * 脉宽由策略控制（默认 100 ms，见 configs/sync.yaml），到点后拉低；
  * 同一套事件流既能跑真实 PsychoPy，也能在无显示器环境下被完整仿真与断言。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from .timing import PulsePolicy
from .trigger_mapping import PhysicalTriggerMap


# ------------------------------------------------------------------ 线路抽象
class TriggerLine(Protocol):
    def set_high(self, code: int) -> None: ...
    def set_low(self) -> None: ...


class SimulatedLine:
    """无头模式：记录每次电平变化（用于断言脉宽与对齐）。"""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self.edges: list[tuple[float, str, int | None]] = []
        self._high_since: float | None = None
        self._current: int | None = None

    def set_high(self, code: int) -> None:
        now = self._clock()
        self.edges.append((now, "high", int(code)))
        self._high_since = now
        self._current = int(code)

    def set_low(self) -> None:
        if self._high_since is None:
            return
        self.edges.append((self._clock(), "low", self._current))
        self._high_since = None
        self._current = None

    @property
    def codes(self) -> list[int]:
        return [c for _, level, c in self.edges if level == "high" and c is not None]

    def pulse_widths(self) -> list[float]:
        widths, high_at = [], None
        for t, level, _ in self.edges:
            if level == "high":
                high_at = t
            elif high_at is not None:
                widths.append(t - high_at)
                high_at = None
        return widths


class ParallelLine:
    """真机模式：PsychoPy 并行口（Windows）。"""

    def __init__(self, address: int = 0x0378) -> None:
        from psychopy import parallel

        self._port = parallel.ParallelPort(address=address)
        self._port.setData(0)

    def set_high(self, code: int) -> None:
        self._port.setData(int(code))

    def set_low(self) -> None:
        self._port.setData(0)


# ------------------------------------------------------------------ 脉宽控制
@dataclass
class TriggerPulse:
    """Logical event -> physical TTL pulse state machine.

    arm() receives the stable BPlus logical event code.

    When a PhysicalTriggerMap is configured, the mapped physical code is
    written to the trigger line while software events retain the logical code.
    """

    line: TriggerLine
    policy: PulsePolicy
    clock: Callable[[], float] = time.perf_counter
    mapper: PhysicalTriggerMap | None = None
    events: list[tuple[float, int]] = field(default_factory=list)
    physical_events: list[tuple[float, int]] = field(default_factory=list)
    _raised_at: float | None = None
    _code: int | None = None

    def arm(self, code: int) -> None:
        logical_code = int(code)

        physical_code = (
            self.mapper.to_physical(logical_code)
            if self.mapper is not None
            else logical_code
        )

        if self._raised_at is not None:
            self.line.set_low()

        self.line.set_high(physical_code)
        self._raised_at = self.clock()
        self._code = logical_code

        self.events.append((self._raised_at, logical_code))
        self.physical_events.append((self._raised_at, physical_code))

    def poll(self) -> bool:
        """If pulse width has elapsed, lower the line and return True."""
        if self._raised_at is None:
            return False

        if (self.clock() - self._raised_at) * 1000.0 >= self.policy.width_ms:
            self.line.set_low()
            self._raised_at = None
            self._code = None
            return True

        return False


# ------------------------------------------------------------------ 窗口抽象
class WindowLike(Protocol):
    def call_on_flip(self, fn: Callable, *args) -> None: ...
    def flip(self) -> float: ...
    def wait_until(self, t: float) -> None: ...


class NullWindow:
    """无头窗口：默认按虚拟帧时钟推进（每 flip 前进 frame_s），可选实时节奏。

    虚拟时钟让 DEMO/CI 也能得到**有物理意义**的脉宽与对齐结果（而不是全部 0 ms）。
    """

    def __init__(self, *, speed: float = 0.0, frame_s: float = 1.0 / 60.0,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self._callbacks: list[tuple[Callable, tuple]] = []
        self._frame_hooks: list[Callable[[], object]] = []
        self._t0 = clock()
        self._clock = clock
        self.speed = speed
        self.frame_s = frame_s
        self._virtual = 0.0
        self.flip_times: list[float] = []

    def now(self) -> float:
        if self.speed <= 0:
            return self._virtual
        return (self._clock() - self._t0) * self.speed

    def call_on_flip(self, fn: Callable, *args) -> None:
        self._callbacks.append((fn, args))

    def add_frame_hook(self, fn: Callable[[], object]) -> None:
        """每帧都执行（用于脉宽轮询），对应真实设备的每帧循环。"""
        self._frame_hooks.append(fn)

    def flip(self) -> float:
        for fn, args in self._callbacks:      # 一次性：与本次 flip 同帧
            fn(*args)
        self._callbacks.clear()
        t = self.now()
        self.flip_times.append(t)
        for hook in self._frame_hooks:        # 每帧：脉宽到点则拉低
            hook()
        self._virtual += self.frame_s
        return t

    def wait_until(self, t: float) -> None:
        guard = 0
        while self.now() < t:
            self.flip()
            guard += 1
            if guard > 2_000_000:                       # 安全阀：避免时间轴错误导致死循环
                raise RuntimeError(f"wait_until({t}) 未能在 2e6 帧内到达（检查事件时间轴）")
            if self.speed > 0:
                time.sleep(min(0.005, max(0.0, t - self.now())))


class PsychoPyWindow:
    """真机窗口：真正的 PsychoPy（懒加载，未安装时 import 才失败）。"""

    def __init__(self, *, size=(1920, 1080), fullscreen: bool = True, units: str = "pix") -> None:
        from psychopy import visual

        from psychopy import core

        self._visual = visual
        self._frame_hooks: list[Callable[[], object]] = []
        self._clock = core.Clock()
        self.win = visual.Window(size=size, fullscr=fullscreen, units=units, color="black")

    def call_on_flip(self, fn: Callable, *args) -> None:
        self.win.callOnFlip(fn, *args)

    def reset_clock(self) -> None:
        """Start the formal paradigm clock after instructions/countdown."""
        self._clock.reset()

    def add_frame_hook(self, fn: Callable[[], object]) -> None:
        self._frame_hooks.append(fn)

    def flip(self) -> float:
        t = float(self.win.flip())
        for hook in self._frame_hooks:
            hook()                            # vsync 之后立刻检查脉宽是否到点
        return t

    def wait_until(self, t: float) -> None:
        """在虚拟/实验时间轴上等到 t（每次 flip 前进一帧，同时跑 frame hook 轮询脉宽）。"""
        guard = 0
        while self._clock.getTime() < t:
            self.flip()
            guard += 1
            if guard > 2_000_000:                     # 安全阀
                raise RuntimeError(f"wait_until({t}) 未能在 2e6 帧内到达")


# ------------------------------------------------------------------ 呈现器
class Presenter(Protocol):
    def draw(self, event) -> None: ...


class NullPresenter:
    """无头模式：只记录"这一帧画了什么"。"""

    def __init__(self, on_draw: Callable[[object], None] | None = None) -> None:
        self.on_draw = on_draw or (lambda ev: None)

    def draw(self, event) -> None:
        self.on_draw(event)


class TextPresenter:
    """真机模式：每个事件显示一段文字（MVP 版；后续按范式细化视觉）。"""

    def __init__(self, window: PsychoPyWindow, labels: dict[int, str] | None = None) -> None:
        self.window = window
        self.labels = labels or {}
        self._stim = window._visual.TextStim(window.win, text="+", color="white", height=48)

    def draw(self, event) -> None:
        label = self.labels.get(int(event.code))
        self._stim.text = label if label is not None else "+"
        self._stim.draw()


# ------------------------------------------------------------------ 运行器
@dataclass
class RunReport:
    paradigm: str
    n_events: int
    onsets_s: list[float]
    codes: list[int]


def run_events(
    events: Iterable,
    *,
    window: WindowLike,
    pulse: TriggerPulse,
    presenter: Presenter,
    paradigm: str = "unknown",
) -> RunReport:
    """按事件流的时间轴逐帧呈现 + 帧同步发码。"""
    onsets, codes = [], []
    ordered = sorted(events, key=lambda e: e.onset)
    if hasattr(window, "add_frame_hook"):
        window.add_frame_hook(pulse.poll)               # 每帧轮询脉宽（关键）
    for ev in ordered:
        window.wait_until(ev.onset)
        window.call_on_flip(pulse.arm, int(ev.code))   # ← 与呈现同帧
        presenter.draw(ev)
        window.flip()
        onsets.append(ev.onset)
        codes.append(int(ev.code))
    # 收尾：确保线上是低电平
    window.wait_until((onsets[-1] if onsets else 0.0) + pulse.policy.width_ms / 1000.0)
    pulse.poll()
    return RunReport(paradigm=paradigm, n_events=len(codes), onsets_s=onsets, codes=codes)
