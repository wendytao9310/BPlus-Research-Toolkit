#!/usr/bin/env python
"""跑单个范式的会话（DEMO 无硬件 / 真机加 --real）。

    python scripts/run_session.py --paradigm nback --participant D01 --session 1 --dummy
    python scripts/run_session.py --paradigm nback --participant P01 --session 1 --real --backend parallel
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.gui import run_session  # noqa: E402
from bplus.gui.runner import ExperimentAborted  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="运行单个范式会话")
    ap.add_argument("--paradigm", default="nback",
                    choices=["rest", "mmn", "vft", "nback", "emotion", "recovery"])
    ap.add_argument("--participant", default="D01")
    ap.add_argument("--session", default="1")
    ap.add_argument("--out", default="data/session")
    ap.add_argument("--dummy", action="store_true", help="无硬件 DEMO（默认）")
    ap.add_argument("--real", action="store_true", help="使用真实 PsychoPy + 触发硬件")
    ap.add_argument("--backend", default="simulated", choices=["simulated", "parallel", "labjack", "lsl"])
    ap.add_argument("--speed", type=float, default=0.0, help="DEMO 倍速（0 = 尽可能快）")
    ap.add_argument("--mode", choices=["DEMO", "VISUAL_DEMO", "PILOT", "REAL"], default=None,
                    help="默认：--real 时为 REAL，否则 DEMO")
    ap.add_argument("--pilot-staff", action="store_true",
                    help="Emotion 在 PILOT 模式下用操作员本人测试时的显式确认")
    ap.add_argument("--visual-demo", action="store_true",
                    help="打开 PsychoPy 窗口但使用模拟触发，不连接采集硬件")
    args = ap.parse_args(argv)

    try:
        res = run_session(args.paradigm, args.participant, args.session, args.out,
                          dummy=not args.real, backend=args.backend, speed=args.speed,
                          mode=args.mode, pilot_staff=args.pilot_staff, visual_demo=args.visual_demo)
    except ExperimentAborted as exc:
        print(f"[ABORTED] {exc}")
        return 130
    print(f"paradigm : {res.paradigm}")
    print(f"trials   : {len(res.trials)}")
    print(f"behavior : {res.behavior_log}")
    print(f"triggers : {res.trigger_log}")
    print("summary  :")
    print(json.dumps(res.summary, ensure_ascii=False, indent=2, default=str))
    for n in res.notes:
        print("note     :", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
