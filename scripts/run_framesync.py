#!/usr/bin/env python
"""帧同步呈现跑一遍（DEMO 用无头仿真；真机加 --psychopy）。

    python scripts/run_framesync.py --paradigm mmn                 # 无头仿真
    python scripts/run_framesync.py --paradigm nback --psychopy     # 真机（需 PsychoPy + 并行口/LabJack）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod  # noqa: E402
from bplus.paradigms import REGISTRY  # noqa: E402
from bplus.realtime import (NullPresenter, NullWindow, ParallelLine, PsychoPyWindow,  # noqa: E402
                            SimulatedLine, TextPresenter, TriggerPulse, run_events)
from bplus.timing import PulsePolicy, check_events  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="帧同步呈现（callOnFlip 发码）")
    ap.add_argument("--paradigm", default="mmn", choices=sorted(REGISTRY))
    ap.add_argument("--psychopy", action="store_true", help="使用真实 PsychoPy 窗口")
    ap.add_argument("--parallel-address", default="0x0378")
    args = ap.parse_args(argv)

    policy = PulsePolicy.from_config(cfg_mod.load_yaml("sync.yaml"))
    if policy.problems():
        print("触发策略不合法：")
        for p in policy.problems():
            print("  -", p)
        return 2

    cfg = cfg_mod.paradigm_config(args.paradigm)
    events = REGISTRY[args.paradigm](cfg).events()
    issues = check_events(events, policy)
    if issues:
        print("事件间隔与脉宽冲突：")
        for i in issues[:5]:
            print("  -", i)
        return 2

    print(f"paradigm     : {args.paradigm}")
    print(f"events       : {len(events)}")
    print(f"pulse policy : {policy.capture_rule()}")
    print(f"fNIRS 量化   : ±{policy.max_event_quantisation_ms():.0f} ms（一个采样周期）")

    if args.psychopy:
        window = PsychoPyWindow()
        presenter = TextPresenter(window)
        line = ParallelLine(address=int(args.parallel_address, 16))
    else:
        window = NullWindow(speed=0.0)          # 虚拟帧时钟：DEMO 也能量出真实脉宽
        presenter = NullPresenter()
        line = SimulatedLine(clock=window.now)

    pulse = TriggerPulse(line=line, policy=policy, clock=window.now)
    report = run_events(events, window=window, pulse=pulse, presenter=presenter,
                        paradigm=args.paradigm)

    print(f"\n已发触发   : {len(report.codes)} 个")
    print(f"前 6 个码  : {report.codes[:6]}")
    if isinstance(line, SimulatedLine):
        widths = [round(w * 1000, 1) for w in line.pulse_widths()]
        ok = all(abs(w - policy.width_ms) <= 30 for w in widths) if widths else False
        print(f"脉宽样本   : {widths[:6]} ms（目标 {policy.width_ms:.0f} ms，虚拟帧时钟）")
        print(f"脉宽检查   : {'OK' if ok else 'FAIL：脉宽偏离目标，请检查帧率与 poll 逻辑'}")
    print("\n提示：真机运行时，触发由 win.callOnFlip() 挂在下一次 flip 上，与刺激呈现同帧。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
