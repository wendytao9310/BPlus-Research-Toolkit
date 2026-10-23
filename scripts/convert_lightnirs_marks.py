#!/usr/bin/env python
"""LIGHTNIRS 导出的标记列 → sync_check 需要的 `code,t` CSV（PILOT-0 阶段 A4）。

    # 用列映射文件（推荐：configs/lightnirs_columns.yaml 已填真实列名）
    python scripts/convert_lightnirs_marks.py --csv lightnirs.csv \
        --map configs/lightnirs_columns.yaml --out data/sync/lightnirs_marks.csv

    # 或直接指定列名
    python scripts/convert_lightnirs_marks.py --csv lightnirs.csv \
        --time-col "Time(s)" --marker-col Mark --out …

    # 模式：auto（默认）/ event（只有事件行有值）/ change（连续通道，值变化即事件）
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _num(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in {"", "-", "--", "nan", "None", "0", "0.0"}:
        return None
    m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", s)
    return float(m.group(0)) if m else None


def load_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8-sig", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def guess_mode(rows: list[dict], marker_col: str) -> str:
    nonempty = sum(1 for r in rows if _num(r.get(marker_col)) is not None)
    if len(rows) and nonempty / len(rows) < 0.2:
        return "event"
    return "change"


def extract(rows: list[dict], time_col: str, marker_col: str, mode: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    last = None
    for r in rows:
        t = _num(r.get(time_col))
        code = _num(r.get(marker_col))
        if t is None or code is None:
            continue
        code = int(round(code))
        if mode == "event":
            if code != 0:
                out.append((code, t))
        else:                                            # change：值变化即事件
            if last is None or code != last:
                if code != 0:
                    out.append((code, t))
                last = code
    return sorted(out, key=lambda x: x[1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="LIGHTNIRS 标记列 → code,t CSV")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--map", help="列映射 yaml（configs/lightnirs_columns.yaml）")
    ap.add_argument("--time-col"); ap.add_argument("--marker-col")
    ap.add_argument("--mode", default="auto", choices=["auto", "event", "change"])
    ap.add_argument("--time-unit", default="auto", choices=["auto", "s", "ms"])
    ap.add_argument("--out", default="data/sync/lightnirs_marks.csv")
    args = ap.parse_args(argv)

    mapping = {}
    if args.map:
        import yaml
        map_path = Path(args.map)
        if not map_path.exists():
            map_path = Path("configs") / map_path.name
        mapping = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    time_col = args.time_col or mapping.get("time_column")
    marker_col = args.marker_col or mapping.get("marker_column")
    if not time_col or not marker_col:
        raise SystemExit("缺少列名：请用 --time-col/--marker-col 指定，或先填好 "
                         "configs/lightnirs_columns.yaml（time_column / marker_column）")

    header, rows = load_rows(Path(args.csv))
    for name in (time_col, marker_col):
        if name not in header:
            raise SystemExit(f"列 {name!r} 不在文件里。\n  实际表头：{header[:14]}\n"
                             f"  提示：LIGHTNIRS 列名区分大小写与空格")

    mode = guess_mode(rows, marker_col) if args.mode == "auto" else args.mode
    print(f"列：time={time_col!r} marker={marker_col!r}  模式={mode}"
          + ("（auto：非空标记行 <20%）" if args.mode == "auto" else ""))
    pairs = extract(rows, time_col, marker_col, mode)

    if args.time_unit == "auto":
        vmax = max((t for _, t in pairs), default=0.0)
        scale, note = ((1 / 1000.0, f"ms（auto：最大值 {vmax:.0f}）") if vmax > 1000
                       else (1.0, "s（auto）"))
    else:
        scale, note = ((1 / 1000.0, "ms") if args.time_unit == "ms" else (1.0, "s"))
    pairs = [(c, t * scale) for c, t in pairs]
    print(f"时间单位：{note}")

    if not pairs:
        print("⚠️ 没有解析出任何标记。请检查：列名是否正确、标记是否真的写入了导出文件（F3）")
        return 1
    codes = {}
    for c, _ in pairs:
        codes[c] = codes.get(c, 0) + 1
    print(f"标记：{len(pairs)} 个，码分布 {dict(sorted(codes.items()))}，"
          f"时间范围 {pairs[0][1]:.3f}–{pairs[-1][1]:.3f} s")

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["code", "t"])
        for c, t in pairs:
            w.writerow([c, f"{t:.6f}"])
    print(f"→ {out}\n下一步：python scripts/sync_check.py compare --eeg <curry_events.csv> "
          f"--fnirs {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
