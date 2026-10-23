#!/usr/bin/env python
"""CURRY/Neuroscan 事件 → sync_check 需要的 `code,t` CSV（PILOT-0 阶段 A3）。

三种输入：

    # ① 直接从原始文件取事件（推荐；需 mne + curryreader）
    python scripts/convert_curry_events.py --mne curry_export.cnt --out data/sync/curry_events.csv

    # ② CURRY 导出的"事件列表"CSV（列名自动识别）
    python scripts/convert_curry_events.py --csv events.csv --time-unit auto --out …

    # ③ 自由文本（例如 "Code: 101 Time: 12.345 s"）
    python scripts/convert_curry_events.py --txt events.txt --out …

    # 可选：把事件名映射成我们的触发码
    python scripts/convert_curry_events.py --csv events.csv --code-map "standard=101,deviant=102"
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CODE_HINTS = ("code", "type", "event", "stim", "trigger", "marker", "value", "标记", "事件")
TIME_HINTS = ("time", "onset", "latency", "timestamp", "sec", "second", "sample", "时间")


def _pick(header: list[str], hints) -> str | None:
    low = [h.lower() for h in header]
    for hint in hints:
        for i, h in enumerate(low):
            if hint in h:
                return header[i]
    return None


def _to_seconds(value: str, unit: str) -> float:
    v = float(value)
    if unit == "ms":
        return v / 1000.0
    if unit == "samples":
        raise ValueError("需要 --fs 才能把 sample 转成秒")
    return v


def _normalise_unit(values: list[float], unit: str) -> tuple[float, str]:
    """auto：若最大值 > 1000 且最小值 ≥0，且像"样本/毫秒"，则按 ms 处理（并提示）。"""
    if unit != "auto":
        return (1 / 1000.0 if unit == "ms" else 1.0), unit
    vmax = max(values) if values else 0.0
    if vmax > 1000:
        return 1 / 1000.0, "ms（auto：最大值 %.0f > 1000）" % vmax
    return 1.0, "s（auto）"


def parse_csv(path: Path, *, code_map: dict[str, int], time_unit: str) -> list[tuple[int, float]]:
    with path.open(newline="", encoding="utf-8-sig", errors="ignore") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} 没有数据行")
    header = list(rows[0])
    code_col, time_col = _pick(header, CODE_HINTS), _pick(header, TIME_HINTS)
    if not code_col or not time_col:
        raise SystemExit(f"无法自动识别列名。\n  表头：{header}\n"
                         f"  请用 --code-col/--time-col 指定（也可以用 --txt 模式）")
    raw_time = [float(r[time_col]) for r in rows if r.get(time_col) not in (None, "")]
    scale, unit_note = _normalise_unit(raw_time, time_unit)
    print(f"列识别：code={code_col!r}  time={time_col!r}  时间单位：{unit_note}")
    out = []
    for r in rows:
        raw_code = (r.get(code_col) or "").strip()
        if not raw_code:
            continue
        try:
            code = int(float(raw_code))
        except ValueError:
            if raw_code.lower() in code_map:
                code = code_map[raw_code.lower()]
            else:
                print(f"  跳过无法解释的码：{raw_code!r}（可在 --code-map 里登记）")
                continue
        if code == 0:
            continue                                   # 0 = 无事件
        out.append((code, float(r[time_col]) * scale))
    return sorted(out, key=lambda x: x[1])


def parse_txt(path: Path, *, code_map: dict[str, int], time_unit: str) -> list[tuple[int, float]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    pairs = []
    for m in re.finditer(r"(?:code|type|event|marker|事件)[^0-9A-Za-z]{0,4}([0-9]+)[^0-9]{0,20}?"
                         r"(?:time|onset|latency|时间)[^0-9]{0,4}([0-9]+(?:\.[0-9]+)?)", text, re.I):
        pairs.append((int(m.group(1)), float(m.group(2))))
    if not pairs:                                        # 退化：纯 "code time" 两列
        for line in text.splitlines():
            nums = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", line)
            if len(nums) >= 2:
                pairs.append((int(float(nums[0])), float(nums[1])))
    raw_time = [t for _, t in pairs]
    scale, note = _normalise_unit(raw_time, time_unit)
    print(f"文本解析：{len(pairs)} 条  时间单位：{note}")
    return sorted(((c, t * scale) for c, t in pairs), key=lambda x: x[1])


def parse_mne(path: Path, *, stim_channel: str | None, fs: float | None) -> list[tuple[int, float]]:
    try:
        import mne
    except ImportError:
        raise SystemExit("需要 mne：uv pip install mne curryreader")
    suffix = path.suffix.lower()
    reader = {".cdt": mne.io.read_raw_curry, ".dap": mne.io.read_raw_curry,
              ".dat": mne.io.read_raw_curry, ".cnt": mne.io.read_raw_cnt,
              ".edf": mne.io.read_raw_edf}.get(suffix)
    if reader is None:
        raise SystemExit(f"不支持的后缀 {suffix}（支持 .cdt/.cnt/.edf）")
    raw = reader(str(path), preload=True, verbose="ERROR")
    rate = fs or float(raw.info["sfreq"])
    try:
        events = mne.find_events(raw, stim_channel=stim_channel, verbose="ERROR")
    except Exception as exc:
        raise SystemExit(f"find_events 失败：{exc}\n  提示：用 --stim-channel 指定触发通道名，"
                         f"当前通道：{raw.ch_names[:12]}")
    print(f"读取 {path.name}：{len(raw.ch_names)} 通道，{rate:g} Hz，找到 {len(events)} 个事件")
    return sorted(((int(e[2]), float(e[0]) / rate) for e in events), key=lambda x: x[1])


def diagnose(pairs: list[tuple[int, float]], label: str) -> None:
    if not pairs:
        print(f"⚠️ {label}：没有解析出任何事件"); return
    codes = {}
    for c, _ in pairs:
        codes[c] = codes.get(c, 0) + 1
    span = pairs[-1][1] - pairs[0][1]
    print(f"{label}：{len(pairs)} 个事件，码分布 {dict(sorted(codes.items()))}，"
          f"时间范围 {pairs[0][1]:.3f}–{pairs[-1][1]:.3f} s（跨度 {span:.3f} s）")
    if len(pairs) > 1:
        gaps = [b[1] - a[1] for a, b in zip(pairs, pairs[1:])]
        print(f"  最小间隔 {min(gaps)*1000:.1f} ms；若 < 脉宽(100 ms) 需检查是否重复打标")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CURRY/Neuroscan 事件 → code,t CSV")
    ap.add_argument("--mne"); ap.add_argument("--csv"); ap.add_argument("--txt")
    ap.add_argument("--stim-channel", default=None)
    ap.add_argument("--fs", type=float, default=None, help="原始文件采样率（覆盖自动读取）")
    ap.add_argument("--time-unit", default="auto", choices=["auto", "s", "ms", "samples"])
    ap.add_argument("--code-map", default="", help="事件名→码，如 standard=101,deviant=102")
    ap.add_argument("--out", default="data/sync/curry_events.csv")
    args = ap.parse_args(argv)

    code_map = {}
    for pair in filter(None, args.code_map.split(",")):
        name, _, code = pair.partition("=")
        code_map[name.strip().lower()] = int(code)
    if code_map:
        print(f"事件名映射：{code_map}")

    if args.mne:
        pairs = parse_mne(Path(args.mne), stim_channel=args.stim_channel, fs=args.fs)
    elif args.csv:
        pairs = parse_csv(Path(args.csv), code_map=code_map, time_unit=args.time_unit)
    elif args.txt:
        pairs = parse_txt(Path(args.txt), code_map=code_map, time_unit=args.time_unit)
    else:
        ap.error("至少要指定 --mne / --csv / --txt 之一")

    diagnose(pairs, "解析结果")
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["code", "t"])
        for c, t in pairs:
            w.writerow([c, f"{t:.6f}"])
    print(f"→ {out}\n下一步：python scripts/sync_check.py compare --eeg {out} --fnirs <lightnirs_marks.csv>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
