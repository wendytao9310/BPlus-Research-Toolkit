#!/usr/bin/env python
"""REAL MODE 启用清单：把 validate 的阻断项翻译成"谁去做什么"。

    python scripts/emotion_enable_checklist.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import validate_library  # noqa: E402

OWNER = [
    ("manifest.csv 为空", "研究团队", "采集/登记刺激（`emotion_library.py scan`）"),
    ("技术 QC", "研究团队", "重跑 `emotion_library.py qc`，修正尺寸/亮度/对比度"),
    ("重复刺激", "研究团队", "保留更优者，其余移入 `rejected/`；用 contact sheet 人工复核"),
    ("年龄适配", "研究团队 + 2 名评定者", "逐张填写 `review/review_rater*.csv` 后 `emotion_review_sheet.py merge`"),
    ("文化适配", "同上", "同上（13 项清单）"),
    ("伦理状态", "PI / 伦理委员会", "取得批件，把批件号写入 manifest.notes（`emotion_library.py provenance`）"),
    ("临床审阅", "临床团队", "审阅负性刺激并把 clinical_review 改为 YES"),
    ("VALIDATION_REPORT", "研究团队", "执行 PILOT 后重跑 `emotion_library.py report`"),
    ("PILOT_PROTOCOL", "研究团队", "确认 `PILOT_PROTOCOL.md` 存在且已按方案执行"),
    ("临床团队批准", "临床负责人", "签署 `CLINICAL_APPROVAL.md`（含 APPROVED）"),
    ("version", "研究团队", "给每张刺激分配 version"),
]


def main() -> int:
    rep = validate_library()
    print("=" * 78)
    print(f"REAL MODE = {'ENABLED ✅' if rep.ok else 'DISABLED ⛔'}")
    print(f"刺激数：{rep.n_stimuli}　分布：{rep.n_by_condition}")
    print(f"检查：{sum(1 for v in rep.checks.values() if v)}/{len(rep.checks)} 通过")
    print("=" * 78)
    if rep.ok:
        print("全部通过。可执行真实被试采集（Emotion 已解锁）。")
        return 0
    print("距离 ENABLED 还差以下事项：\n")
    print(f"{'阻断项':<46}{'负责人':<20}动作")
    for b in rep.blockers:
        owner, action = "研究团队", "按 VALIDATION_REPORT 逐项处理"
        for key, o, a in OWNER:
            if key in b:
                owner, action = o, a
                break
        print(f"{b[:44]:<46}{owner:<20}{action}")
    print("\n注意：本脚本只是翻译器，**不会**替你生成批准文件。")
    print("      `CLINICAL_APPROVAL.md` 必须由临床人员实际签署后才可出现 APPROVED。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
