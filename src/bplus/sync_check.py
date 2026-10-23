"""PILOT-0 同步体检：发校准脉冲 -> 比对三方时间戳 -> 产出 sync_report。

对应 MASTER COMMAND §59（Synchronization Validation）与决策 D-001/D-002/D-003。

两级判据（均为 PROJECT_ENGINEERING_THRESHOLD，不是国际标准）：
  1) 首要：脉冲不丢失（数量与码序列完全一致）—— "能不能用"的门槛；
  2) 其次：offset 与 jitter 在容差内 —— "对齐得好不好"。
容差默认：|offset| <= 一个 fNIRS 采样周期（75 ms），jitter SD <= 40 ms。
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

FROZEN_TOLERANCE_MS = {"offset": 75.0, "jitter_sd": 40.0, "fnirs_quantisation": 75.0}


@dataclass
class Pulse:
    code: int
    t: float          # 秒，相对该设备记录起点


@dataclass
class SyncReport:
    session: str
    n_expected: int
    n_eeg: int
    n_fnirs: int
    missing_codes: list = field(default_factory=list)
    offset_ms: float | None = None
    jitter_sd_ms: float | None = None
    verdict: str = "INCONCLUSIVE"
    reasons: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "session": self.session,
            "expected_pulses": self.n_expected,
            "counts": {"eeg": self.n_eeg, "fnirs": self.n_fnirs},
            "missing_codes": self.missing_codes,
            "offset_ms": self.offset_ms,
            "jitter_sd_ms": self.jitter_sd_ms,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "tolerance": FROZEN_TOLERANCE_MS,
            "evidence_status": "PROJECT_ENGINEERING_THRESHOLD",
            "notes": [
                "fNIRS 事件时间戳存在一个采样周期(75 ms)的量化，单次误差可达 ±37.5 ms",
                "判定顺序：先看是否丢脉冲，再看 offset/jitter",
            ],
        }


def read_pulses(path, *, code_col: str = "code", time_col: str = "t"):
    """读取设备导出的事件列（CSV，含 code 与时间列；时间单位秒）。"""
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rows.append(Pulse(code=int(float(r[code_col])), t=float(r[time_col])))
    return sorted(rows, key=lambda p: p.t)


def compare(expected, eeg, fnirs, *, session: str = "unknown") -> SyncReport:
    rep = SyncReport(session=session, n_expected=len(expected), n_eeg=len(eeg), n_fnirs=len(fnirs))
    got = [p.code for p in fnirs]
    rep.missing_codes = [c for c in expected if c not in got]
    if rep.missing_codes or len(eeg) != len(expected) or len(fnirs) != len(expected):
        rep.verdict = "FAIL"
        rep.reasons.append(
            "脉冲数量不一致（期望 %d，EEG %d，fNIRS %d），丢失码 %s"
            % (len(expected), len(eeg), len(fnirs), rep.missing_codes)
        )
        return rep
    # ⚠️ 必须按**时间顺序逐位配对**，而不是按码排序：
    #    同一个码会重复出现（例如 101 出现 5 次），按码排序会把不相关的事件配到一起，
    #    结果是"jitter 巨大"这种误导性的报错（本项目实测出现 2449 ms 的假 jitter）。
    eeg_ordered = sorted(eeg, key=lambda p: p.t)
    fnirs_ordered = sorted(fnirs, key=lambda p: p.t)
    seq_eeg = [p.code for p in eeg_ordered]
    seq_fnirs = [p.code for p in fnirs_ordered]
    if seq_eeg != seq_fnirs:
        rep.verdict = "FAIL"
        rep.reasons.append(
            "两侧码序列不一致（可能是漏抓或码表不匹配）\n"
            f"      EEG : {seq_eeg}\n      fNIRS: {seq_fnirs}")
        return rep
    deltas = [(f.t - e.t) * 1000.0 for e, f in zip(eeg_ordered, fnirs_ordered)]
    rep.offset_ms = round(statistics.fmean(deltas), 3)
    rep.jitter_sd_ms = round(statistics.pstdev(deltas), 3) if len(deltas) > 1 else 0.0
    if abs(rep.offset_ms) > FROZEN_TOLERANCE_MS["offset"]:
        rep.reasons.append("|offset| %.1f ms 超过容差 %.0f ms" % (abs(rep.offset_ms), FROZEN_TOLERANCE_MS["offset"]))
    if (rep.jitter_sd_ms or 0.0) > FROZEN_TOLERANCE_MS["jitter_sd"]:
        rep.reasons.append("jitter SD %.1f ms 超过容差 %.0f ms" % (rep.jitter_sd_ms, FROZEN_TOLERANCE_MS["jitter_sd"]))
    if not rep.reasons:
        rep.reasons.append("脉冲齐全且 offset/jitter 在容差内")
    rep.verdict = "PASS" if not [r for r in rep.reasons if "超过" in r or "不一致" in r] else "FAIL"
    return rep


def write_report(rep: SyncReport, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    j = out / "sync_report.json"
    j.write_text(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    d = rep.as_dict()
    rows = "".join("<tr><td>%s</td><td>%s</td></tr>" % (k, json.dumps(v, ensure_ascii=False)) for k, v in d.items())
    color = {"PASS": "#16a34a", "FAIL": "#dc2626", "INCONCLUSIVE": "#d97706"}[rep.verdict]
    html = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        "<title>sync_report</title>"
        '<style>body{font:14px/1.6 -apple-system,"PingFang SC",sans-serif;margin:24px}'
        "table{border-collapse:collapse}td{border:1px solid #ddd;padding:6px 10px;vertical-align:top}"
        ".v{font-size:20px;font-weight:700;color:" + color + "}</style>"
        "<h1>同步体检报告 · " + rep.session + "</h1>"
        '<p class="v">' + rep.verdict + "</p><table>" + rows + "</table>"
        '<p style="color:#666">容差为 PROJECT_ENGINEERING_THRESHOLD（非国际标准）；'
        "fNIRS 事件时间戳量化 = 一个采样周期 75 ms。</p></html>"
    )
    h = out / "sync_report.html"
    h.write_text(html, encoding="utf-8")
    return j, h


def calibrate(codes, *, interval_s: float, pulse):

    """发校准脉冲。

    所有物理 TTL 输出必须经过 TriggerPulse：
    - 保证 HIGH 保持时间
    - 自动 LOW
    - 避免 legacy backend.emit() 瞬时脉冲
    """

    sent = []

    t0 = time.perf_counter()

    for i, code in enumerate(codes):

        while time.perf_counter() - t0 < i * interval_s:
            time.sleep(0.001)

        pulse.arm(code)

        stamp = time.perf_counter() - t0

        sent.append(Pulse(code=code, t=stamp))

        # 等待 TTL 脉宽结束
        time.sleep(pulse.policy.width_ms / 1000.0)

        pulse.poll()

    return sent
