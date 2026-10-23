#!/usr/bin/env python
"""刺激人工审核工作表：生成（generate）与合并（merge）。

    # 生成给 2 名研究者的审核表（CSV + 可视化 HTML）
    python scripts/emotion_review_sheet.py generate

    # 收表后合并回 manifest（不一致的条目保持 PENDING，并写入 review/conflicts.csv）
    python scripts/emotion_review_sheet.py merge \
        --rater1 stimuli/emotion/review/review_rater1.csv \
        --rater2 stimuli/emotion/review/review_rater2.csv

    # 登记伦理批件号与同意书编号（写入 manifest.notes）
    python scripts/emotion_library.py provenance --ethics-id ETH-2026-001 --consent-id MC-2026-001
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import REQUIRED_COLUMNS, load_manifest  # noqa: E402

CHECK_ITEMS = [
    ("no_child_inappropriate", "不包含儿童不适宜内容"),
    ("no_violence", "无暴力"),
    ("no_gore", "无血腥"),
    ("no_porn", "无色情"),
    ("no_self_harm", "无自伤内容"),
    ("no_horror", "无明显恐怖刺激"),
    ("face_clear", "面部清晰"),
    ("emotion_clear", "情绪表达明确"),
    ("age_ok", "年龄适配"),
    ("culture_ok", "文化适配"),
    ("no_artifact", "无明显视觉伪影"),
    ("licence_clear", "版权明确"),
    ("ethics_clear", "伦理状态明确"),
]


def generate(root: Path) -> int:
    records = load_manifest(root)
    if not records:
        print("manifest.csv 为空"); return 2
    out = root / "review"
    out.mkdir(parents=True, exist_ok=True)
    for rater in ("rater1", "rater2"):
        with (out / f"review_{rater}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["stimulus_id", "condition", "file"] + [k for k, _ in CHECK_ITEMS] + ["notes"])
            for r in records:
                w.writerow([r.stimulus_id, r.condition, r.file] + [""] * len(CHECK_ITEMS) + [""])
    rows = "".join(f"""<figure><img src="../{html.escape(r.file)}"/>
<figcaption><b>{html.escape(r.stimulus_id)}</b><br/>{html.escape(r.condition)}<br/>
{''.join(f'<label><input type=checkbox/> {html.escape(label)}</label>' for _, label in CHECK_ITEMS[:4])}
</figcaption></figure>""" for r in records)
    (out / "review_sheet.html").write_text(f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>刺激人工审核表</title><style>body{{font:13px -apple-system,"PingFang SC",sans-serif;margin:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}}
figure{{margin:0;background:#fff;border-radius:10px;padding:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
img{{width:100%;border-radius:6px}}label{{display:block;font-size:11px}}figcaption{{font-size:11px}}</style>
<h1>刺激人工审核表（13 项见 AGE_CULTURAL_ETHICS.md）</h1>
<p>请对照 CSV（<code>review_rater1.csv</code> / <code>review_rater2.csv</code>）逐张填写 YES/NO/NA。</p>
<div class="grid">{rows}</div></html>""", encoding="utf-8")
    print(f"已生成 {out}/review_rater1.csv、review_rater2.csv、review_sheet.html（{len(records)} 张）")
    return 0


def _read(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {r["stimulus_id"]: r for r in csv.DictReader(fh)}


def merge(root: Path, rater_files: list[Path]) -> int:
    sheets = [_read(p) for p in rater_files]
    records = {r.stimulus_id: r for r in load_manifest(root)}
    conflicts, updated = [], 0
    for sid, rec in records.items():
        votes = {key: [] for key, _ in CHECK_ITEMS}
        for sh in sheets:
            row = sh.get(sid)
            if not row:
                continue
            for key, _ in CHECK_ITEMS:
                v = (row.get(key) or "").strip().upper()
                if v in {"YES", "Y", "1", "TRUE"}:
                    votes[key].append(True)
                elif v in {"NO", "N", "0", "FALSE"}:
                    votes[key].append(False)
        if not any(votes.values()):
            continue                                     # 没人填这张
        bad = [k for k, v in votes.items() if v and not all(v)]
        if bad:
            conflicts.append({"stimulus_id": sid, "items": ",".join(bad)})
            continue
        if all(votes[k] for k, _ in CHECK_ITEMS):
            rec.age_suitability = "YES"
            rec.cultural_suitability = "YES"
            rec.ethics_status = "YES"
            if rec.duplicate_of:
                continue
            rec.technical_qc = rec.technical_qc or "PASS"
            updated += 1
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=REQUIRED_COLUMNS)
        w.writeheader()
        for rec in records.values():
            w.writerow({k: getattr(rec, k) for k in REQUIRED_COLUMNS})
    out = root / "review"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "conflicts.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["stimulus_id", "items"])
        w.writeheader(); w.writerows(conflicts)
    print(f"合并完成：{updated} 张通过全部 13 项 → manifest 已标记 YES；"
          f"{len(conflicts)} 张存在分歧 → review/conflicts.csv（需第三名评定者裁决）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="刺激人工审核工作表")
    ap.add_argument("--root", default="stimuli/emotion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate").set_defaults(func=lambda a: generate(Path(a.root)))
    m = sub.add_parser("merge")
    m.add_argument("--rater1", required=True); m.add_argument("--rater2", required=True)
    m.add_argument("--rater3")
    m.set_defaults(func=lambda a: merge(Path(a.root), [Path(p) for p in
                                                       [a.rater1, a.rater2, a.rater3] if p]))
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
