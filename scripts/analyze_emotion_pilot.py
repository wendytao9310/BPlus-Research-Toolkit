#!/usr/bin/env python
"""汇总刺激 pilot 评定 → 按 PILOT_PROTOCOL 门槛判定 → 可选择性写回 manifest。

    python scripts/analyze_emotion_pilot.py --dir data/pilot_emotion
    python scripts/analyze_emotion_pilot.py --dir data/pilot_emotion --apply
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import REQUIRED_COLUMNS, load_manifest  # noqa: E402

THRESHOLDS = {                       # 见 PILOT_PROTOCOL.md §2（PROJECT 初值）
    "category_agreement": 0.80,
    "valence": {"positive": 3.5, "neutral": (2.5, 3.5), "negative": 2.5},
    "clarity_min": 4.0,
    "discomfort_max_ratio": 0.10,
}
CATEGORY_CODE = {1: "negative", 2: "neutral", 3: "positive"}


def summarize(rows: list[dict]) -> dict[str, dict]:
    by_stim = defaultdict(list)
    for r in rows:
        by_stim[r["stimulus_id"]].append(r)
    out = {}
    for sid, rs in by_stim.items():
        n = len(rs)
        condition = rs[0]["condition"]
        agree = sum(1 for r in rs if CATEGORY_CODE.get(int(r["category"])) == condition) / n
        out[sid] = {
            "n_raters": n, "condition": condition,
            "valence_mean": statistics.fmean(float(r["valence"]) for r in rs),
            "arousal_mean": statistics.fmean(float(r["arousal"]) for r in rs),
            "intensity_mean": statistics.fmean(float(r["intensity"]) for r in rs),
            "clarity_mean": statistics.fmean(float(r["clarity"]) for r in rs),
            "age_look_mean": statistics.fmean(float(r["age_look"]) for r in rs),
            "culture_fit_mean": statistics.fmean(float(r["culture_fit"]) for r in rs),
            "category_agreement": agree,
            "discomfort_ratio": sum(1 for r in rs if int(r["discomfort"]) >= 2) / n,
        }
    return out


def verdict(s: dict) -> tuple[bool, list[str]]:
    """按 PILOT_PROTOCOL §2 判定。

    ⚠️ 一致性阈值必须是 **n 感知**的：正式 pilot 要求 ≥20 名评定者（用 80%），
    但排练时只有 3–5 人，80% 在统计上不可达（3 人全对才 100%）。因此：
        n ≥ 8 → 80%    （正式 pilot）
        n < 8 → 2/3     （排练；报告中会标注 SMALL_N）
    """
    reasons = []
    cond = s["condition"]
    n = s.get("n_raters", 0)
    need = THRESHOLDS["category_agreement"] if n >= 8 else 2.0 / 3.0
    if s["category_agreement"] + 1e-9 < need:
        reasons.append(f"类别一致性 {s['category_agreement']:.2f} < {need:.2f}"
                       + ("" if n >= 8 else f"（SMALL_N={n}，排练用多数决）"))
    thr = THRESHOLDS["valence"][cond]
    if isinstance(thr, tuple):
        if not (thr[0] <= s["valence_mean"] <= thr[1]):
            reasons.append(f"效价均值 {s['valence_mean']:.2f} 不在 {thr}")
    elif cond == "positive" and s["valence_mean"] < thr:
        reasons.append(f"正性效价 {s['valence_mean']:.2f} < {thr}")
    elif cond == "negative" and s["valence_mean"] > thr:
        reasons.append(f"负性效价 {s['valence_mean']:.2f} > {thr}")
    if s["clarity_mean"] < THRESHOLDS["clarity_min"]:
        reasons.append(f"清晰度 {s['clarity_mean']:.2f} < 4.0")
    if s["discomfort_ratio"] > THRESHOLDS["discomfort_max_ratio"]:
        reasons.append(f"不适比例 {s['discomfort_ratio']:.2f} > 0.10（需临床复核）")
    return (not reasons), reasons


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="刺激 pilot 分析")
    ap.add_argument("--dir", default="data/pilot_emotion")
    ap.add_argument("--root", default="stimuli/emotion")
    ap.add_argument("--apply", action="store_true",
                    help="把通过 pilot 的条目标记 age/cultural=YES（**不会**动 clinical_review）")
    args = ap.parse_args(argv)

    files = sorted(Path(args.dir).glob("*_ratings.csv"))
    if not files:
        print(f"{args.dir} 下没有 *_ratings.csv"); return 2
    rows = []
    for f in files:
        with f.open(newline="", encoding="utf-8-sig") as fh:
            rows.extend(list(csv.DictReader(fh)))
    print(f"读入 {len(files)} 名评定者 / {len(rows)} 条评分")

    summ = summarize(rows)
    passed, failed = [], []
    for sid, s in sorted(summ.items()):
        ok, why = verdict(s)
        s["pass"] = ok; s["reasons"] = "; ".join(why)
        (passed if ok else failed).append(sid)

    root = Path(args.root)
    out_csv = root / "pilot_ratings.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        cols = ["stimulus_id", "condition", "n_raters", "valence_mean", "arousal_mean",
                "intensity_mean", "clarity_mean", "age_look_mean", "culture_fit_mean",
                "category_agreement", "discomfort_ratio", "pass", "reasons"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for sid, s in sorted(summ.items()):
            w.writerow({"stimulus_id": sid, **{k: (round(v, 3) if isinstance(v, float) else v)
                                               for k, v in s.items()}})

    if args.apply and passed:
        records = load_manifest(root)
        n = 0
        for r in records:
            if r.stimulus_id in passed:
                r.age_suitability = "YES"
                r.cultural_suitability = "YES"
                if not r.notes or "pilot=PASS" not in r.notes:
                    r.notes = (r.notes + "; " if r.notes else "") + "pilot=PASS"
                n += 1
        with (root / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=REQUIRED_COLUMNS); w.writeheader()
            for r in records:
                w.writerow({k: getattr(r, k) for k in REQUIRED_COLUMNS})
        print(f"已把 {n} 张标记 age/cultural=YES（clinical_review 仍需临床人员单独签署）")

    report = ["# 刺激 pilot 结果（PILOT_REPORT）", "",
              f"- 评定者：{len(files)} 人　刺激：{len(summ)} 张",
              f"- 一致性判据：{'80%' if len(files) >= 8 else '多数决（2/3，SMALL_N 排练模式；正式 pilot 需 ≥20 人）'}",
              f"- 通过：{len(passed)} 张　未通过：{len(failed)} 张", "",
              "| 刺激 | 条件 | 效价 | 唤醒 | 清晰度 | 类别一致性 | 不适比例 | 判定 | 原因 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for sid, s in sorted(summ.items()):
        report.append(f"| {sid} | {s['condition']} | {s['valence_mean']:.2f} | {s['arousal_mean']:.2f} | "
                      f"{s['clarity_mean']:.2f} | {s['category_agreement']:.2f} | "
                      f"{s['discomfort_ratio']:.2f} | {'✅' if s['pass'] else '❌'} | {s['reasons']} |")
    report += ["", "> 阈值来自 `PILOT_PROTOCOL.md`（PROJECT 初值）。未通过的刺激应移入 `rejected/` "
                   "或调整后重评；`clinical_review` 只能由临床人员签署，本脚本不会代签。"]
    (root / "PILOT_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(f"通过 {len(passed)} / 未通过 {len(failed)} → {out_csv} 与 {root/'PILOT_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
