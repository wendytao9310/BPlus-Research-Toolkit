#!/usr/bin/env python
"""PILOT-0 同步体检工具。

    python scripts/sync_check.py emit --n 10 --interval 1.0 --out data/sync
    python scripts/sync_check.py compare --eeg eeg_events.csv --fnirs fnirs_marks.csv --out data/sync
    python scripts/sync_check.py selftest --out data/sync          # 无设备自检
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.sync_check import Pulse, calibrate, compare, read_pulses, write_report  # noqa: E402
from bplus.realtime import TriggerPulse, ParallelLine, SimulatedLine
from bplus.timing import PulsePolicy
from bplus.config import load_yaml  # noqa: E402

CODES = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]



def cmd_emit(args) -> int:

    out = Path(args.out)

    out.mkdir(parents=True, exist_ok=True)

    policy = PulsePolicy.from_config(
        load_yaml("sync.yaml")
    )

    if args.backend == "simulated":
        line = SimulatedLine()
    else:
        line = ParallelLine()

    pulse = TriggerPulse(
        line=line,
        policy=policy
    )

    codes = CODES[: args.n]

    sent = calibrate(
        codes,
        interval_s=args.interval,
        pulse=pulse
    )

    p = out / ("calibration_%s" % time.strftime("%Y%m%d-%H%M%S"))

    with p.open("w", newline="", encoding="utf-8") as fh:

        w = csv.writer(fh)

        w.writerow(["code", "t"])

        for s in sent:

            w.writerow([s.code, "%.6f" % s.t])


    print(
        "已发 %d 个脉冲（backend=%s），记录：%s"
        % (len(sent), args.backend, p)
    )

    print("脉冲码：", [s.code for s in sent])

    print(
        "接下来：在 CURRY 与 LIGHTNIRS 分别导出事件/标记列，再运行 compare"
    )

    print(
        "验收顺序：[1] 数量与码一致 [2] offset <=75ms [3] jitter SD <=40ms"
    )

    return 0


def cmd_compare(args) -> int:
    expected = [int(c) for c in args.expected.split(",")]
    eeg = read_pulses(args.eeg)
    fnirs = read_pulses(args.fnirs)
    rep = compare(expected, eeg, fnirs, session=args.session)
    j, h = write_report(rep, args.out)
    print("verdict=%s  offset=%s ms  jitter_sd=%s ms" % (rep.verdict, rep.offset_ms, rep.jitter_sd_ms))
    for r in rep.reasons:
        print("  -", r)
    print("报告：%s\n      %s" % (j, h))
    return 0 if rep.verdict == "PASS" else 1


def cmd_selftest(args) -> int:
    import random
    rng = random.Random(7)
    expected = CODES[:10]
    base = [i * 1.0 for i in range(10)]
    eeg = [Pulse(c, t) for c, t in zip(expected, base)]
    fnirs = [Pulse(c, t + 0.037 + rng.gauss(0, 0.010)) for c, t in zip(expected, base)]
    rep = compare(expected, eeg, fnirs, session="selftest")
    j, _ = write_report(rep, args.out)
    print("[selftest] verdict=%s offset=%s ms (真值 37)  jitter_sd=%s ms (真值 10)"
          % (rep.verdict, rep.offset_ms, rep.jitter_sd_ms))
    ok = rep.verdict == "PASS" and abs((rep.offset_ms or 0) - 37) < 6
    rep2 = compare(expected, eeg, fnirs[:-1], session="selftest-missing")
    print("[selftest] 丢 1 个脉冲 -> verdict=%s（应为 FAIL）" % rep2.verdict)
    print("[selftest] 报告：%s" % j)
    return 0 if (ok and rep2.verdict == "FAIL") else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PILOT-0 同步体检")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emit", help="发校准脉冲")
    e.add_argument("--n", type=int, default=10)
    e.add_argument("--interval", type=float, default=1.0)
    e.add_argument("--backend", default="simulated", choices=["simulated", "parallel", "labjack", "lsl"])
    e.add_argument("--out", default="data/sync")
    e.set_defaults(func=cmd_emit)

    c = sub.add_parser("compare", help="比对 EEG / fNIRS 事件列")
    c.add_argument("--eeg", required=True)
    c.add_argument("--fnirs", required=True)
    c.add_argument("--expected", default=",".join(str(x) for x in CODES))
    c.add_argument("--session", default="sub-CALIB_ses-0")
    c.add_argument("--out", default="data/sync")
    c.set_defaults(func=cmd_compare)

    s = sub.add_parser("selftest", help="无设备自检")
    s.add_argument("--out", default="data/sync")
    s.set_defaults(func=cmd_selftest)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
