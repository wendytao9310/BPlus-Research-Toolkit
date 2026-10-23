#!/usr/bin/env python
"""情绪刺激库管理 CLI：scan / qc / validate / sources / contacts / report。

    python scripts/emotion_library.py scan      --dir stimuli/emotion/raw/synthetic --source PROJECT_DESIGNED_SYNTHETIC
    python scripts/emotion_library.py qc
    python scripts/emotion_library.py validate
    python scripts/emotion_library.py contacts
    python scripts/emotion_library.py sources
    python scripts/emotion_library.py report
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import (REQUIRED_COLUMNS, find_duplicates, image_technical_qc, load_manifest,  # noqa: E402
                           load_sources, validate_library, write_validation_json)
from bplus.stimuli.manifest import DEFAULT_ROOT, REAL_MODE_ERROR  # noqa: E402


def _write_manifest(records, root: Path) -> None:
    path = root / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=REQUIRED_COLUMNS)
        w.writeheader()
        for r in records:
            w.writerow({k: getattr(r, k) for k in REQUIRED_COLUMNS})
    print(f"已写入 {path}（{len(records)} 条）")


def cmd_scan(args) -> int:
    root = Path(args.root)
    src = load_sources().get(args.source)
    if not src:
        print(f"未知来源 {args.source}；请先登记到 configs/stimuli/emotion_sources.yaml")
        return 2
    d = Path(args.dir)
    files = sorted([p for p in d.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}])
    if not files:
        print(f"{d} 下没有图片"); return 2
    existing = {r.stimulus_id: r for r in load_manifest(root)}
    records, skipped = [], 0
    for p in files:
        cond = p.stem.split("_")[0].lower()
        if cond not in {"positive", "neutral", "negative"}:
            print(f"  跳过（无法从文件名判断条件）：{p.name}"); skipped += 1; continue
        sid = f"{args.source.lower()}_{cond}_{p.stem}"
        rel = p.relative_to(root).as_posix()
        prev = existing.get(sid)
        if prev and prev.sha256:
            continue                                        # 已登记且已算哈希 → 保持不动
        from bplus.stimuli.manifest import StimulusRecord
        records.append(StimulusRecord(
            stimulus_id=sid, condition=cond, file=rel, source_id=args.source,
            license_status=src.get("license_status", ""),
            age_suitability=args.age_suitability, cultural_suitability=args.cultural_suitability,
            ethics_status=args.ethics_status, clinical_review=args.clinical_review,
            technical_qc="PENDING", version=args.version,
            notes=f"kind={src.get('kind','')}; evidence={src.get('evidence','')}"))
    merged = [r for r in existing.values()] + records
    _write_manifest(merged, root)
    print(f"新增 {len(records)} 条，跳过 {skipped} 条")
    return 0


def cmd_qc(args) -> int:
    root = Path(args.root)
    records = load_manifest(root)
    if not records:
        print("manifest.csv 为空，先 scan"); return 2
    hashes = {}
    for r in records:
        p = root / r.file
        if not p.exists():
            print(f"  缺失：{r.file}"); continue
        q = image_technical_qc(p)
        r.width, r.height = q["width"], q["height"]
        r.sha256, r.luminance_mean = q["sha256"], round(q["luminance_mean"], 5)
        r.luminance_sd, r.contrast_rms = round(q["luminance_sd"], 5), round(q["contrast_rms"], 5)
        ok = (q["width"] >= args.min_size and q["height"] >= args.min_size
              and args.lum_min <= q["luminance_mean"] <= args.lum_max
              and q["contrast_rms"] >= args.contrast_min)
        r.technical_qc = "PASS" if ok else "FAIL"
        hashes[r.stimulus_id] = q["ahash"]
    dupes = find_duplicates(hashes)
    for r in records:
        if r.stimulus_id in dupes:
            r.duplicate_of = dupes[r.stimulus_id]
            r.technical_qc = "FAIL"
    _write_manifest(records, root)
    n_pass = sum(1 for r in records if r.technical_qc == "PASS")
    print(f"技术 QC：{n_pass}/{len(records)} 通过；重复 {len(dupes)} 对")
    return 0


def cmd_validate(args) -> int:
    root = Path(args.root)
    rep = validate_library(root, per_condition=args.per_condition)
    write_validation_json(rep, root / "library_validation.json")
    print(f"REAL MODE={'ENABLED' if rep.ok else 'DISABLED'}  刺激数={rep.n_stimuli}  分布={rep.n_by_condition}")
    for k, v in rep.checks.items():
        print(f"  {'✅' if v else '❌'} {k}")
    if rep.blockers:
        print("\n阻断项：")
        for b in rep.blockers:
            print("  -", b)
        print("\n" + REAL_MODE_ERROR)
    return 0 if rep.ok else 1


def cmd_sources(args) -> int:
    srcs = load_sources()
    print(f"{'ID':<26}{'状态':<42}{'可再分发':<10}{'可自动下载'}")
    for sid, s in srcs.items():
        print(f"{sid:<26}{str(s.get('license_status')):<42}"
              f"{str(bool(s.get('redistribution_allowed'))):<10}{bool(s.get('auto_download_allowed'))}")
    print("\n注意：UNVERIFIED / LICENSE_NONE / THIRD_PARTY_MIRROR_CLAIM 一律不可使用（§5、§8）。")
    return 0


def cmd_prune(args) -> int:
    """移除某个来源的记录（例如真实刺激到位后清掉占位示意图）。"""
    root = Path(args.root)
    records = load_manifest(root)
    keep = [r for r in records if r.source_id != args.source]
    removed = len(records) - len(keep)
    if not removed:
        print(f"没有 source_id={args.source} 的记录"); return 0
    _write_manifest(keep, root)
    print(f"已移除 {removed} 条（source_id={args.source}）；剩余 {len(keep)} 条")
    return 0


def cmd_provenance(args) -> int:
    """把伦理批件号 / 肖像同意书编号写入 manifest.notes（可追溯性的最低要求）。"""
    root = Path(args.root)
    records = load_manifest(root)
    if not records:
        print("manifest.csv 为空"); return 2
    tags = [t for t in (f"ethics_id={args.ethics_id}" if args.ethics_id else None,
                        f"consent_id={args.consent_id}" if args.consent_id else None) if t]
    if not tags:
        print("至少提供 --ethics-id 或 --consent-id"); return 2
    n = 0
    for r in records:
        if args.source and r.source_id != args.source:
            continue
        add = "; ".join(t for t in tags if t.split("=")[0] not in r.notes)
        if add:
            r.notes = (r.notes + "; " if r.notes else "") + add
            n += 1
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=REQUIRED_COLUMNS); w.writeheader()
        for r in records:
            w.writerow({k: getattr(r, k) for k in REQUIRED_COLUMNS})
    print(f"已为 {n} 条刺激写入 {', '.join(tags)}")
    return 0


def cmd_contacts(args) -> int:
    root = Path(args.root)
    records = load_manifest(root)
    if not records:
        print("manifest.csv 为空，先 scan"); return 2
    rows = []
    for r in records:
        p = root / r.file
        rel = Path("..") / ".." / root.name / r.file
        rows.append(f"""<figure><img src="{html.escape(rel.as_posix())}" loading="lazy"/>
<figcaption><b>{html.escape(r.stimulus_id)}</b><br/>{html.escape(r.condition)} ·
{html.escape(r.source_id)}<br/>QC: {html.escape(r.technical_qc)} · {html.escape(r.age_suitability)}</figcaption></figure>""")
    doc = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Emotion contact sheet</title>
<style>body{{font:13px/1.5 -apple-system,"PingFang SC",sans-serif;margin:20px;background:#fafafa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}}
figure{{margin:0;background:#fff;border-radius:10px;padding:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
img{{width:100%;border-radius:6px}}figcaption{{font-size:11px;margin-top:6px;color:#444}}</style>
<h1>情绪刺激 contact sheet（人工审核用）</h1>
<p>共 {len(records)} 张。审核后请把结论写回 manifest.csv 的 age/cultural/ethics/clinical 字段。</p>
<div class="grid">{''.join(rows)}</div></html>"""
    out = root / "preview" / "emotion_contact_sheet.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"contact sheet: {out}")
    try:                                        # 有 matplotlib 时顺带出一张 PDF/PNG
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.image as mpimg
        import matplotlib.pyplot as plt
        n = len(records); cols = 6; rows_n = (n + cols - 1) // cols
        fig, axes = plt.subplots(rows_n, cols, figsize=(cols * 2.2, rows_n * 2.6))
        axes = axes.flatten() if hasattr(axes, "flatten") else [axes]
        for i, r in enumerate(records):
            axes[i].imshow(mpimg.imread(root / r.file), cmap="gray")
            axes[i].set_title(f"{r.condition}\n{r.technical_qc}", fontsize=7)
            axes[i].axis("off")
        for j in range(len(records), len(axes)):
            axes[j].axis("off")
        fig.tight_layout()
        fig.savefig(root / "preview" / "emotion_contact_sheet.png", dpi=140)
        print(f"contact sheet PNG: {root/'preview'/'emotion_contact_sheet.png'}")
    except Exception as exc:                     # pragma: no cover
        print(f"（PNG 版未生成：{exc}）")
    return 0


def cmd_report(args) -> int:
    root = Path(args.root)
    rep = validate_library(root, per_condition=args.per_condition)
    records = load_manifest(root)
    by_cond = rep.n_by_condition
    lines = ["# Emotion 刺激库验证报告（VALIDATION_REPORT）", "",
             f"生成时间：{__import__('datetime').datetime.now().isoformat(timespec='seconds')}", "",
             f"## 状态", "",
             f"- 刺激总数：{rep.n_stimuli}（{by_cond}）",
             f"- REAL MODE：**{'ENABLED' if rep.ok else 'DISABLED'}**",
             f"- 检查项：{sum(1 for v in rep.checks.values() if v)}/{len(rep.checks)} 通过", "",
             "## 检查明细", ""]
    for k, v in rep.checks.items():
        lines.append(f"- [{'x' if v else ' '}] {k}")
    if rep.blockers:
        lines += ["", "## 阻断项（未解决前禁止真实被试）", ""] + [f"- {b}" for b in rep.blockers]
    lines += ["", "## 结论", "",
              "STATUS: COMPLETE" if rep.ok else "STATUS: INCOMPLETE", "",
              "> 本报告的阈值与判定均为 PROJECT 工程规则；授权结论以 emotion_sources.yaml 里的原文引用为准。"]
    (root / "VALIDATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"已写入 {root/'VALIDATION_REPORT.md'}（{'COMPLETE' if rep.ok else 'INCOMPLETE'}）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="情绪刺激库管理")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan"); s.add_argument("--dir", required=True); s.add_argument("--source", required=True)
    s.add_argument("--age-suitability", default="PENDING"); s.add_argument("--cultural-suitability", default="PENDING")
    s.add_argument("--ethics-status", default="PENDING"); s.add_argument("--clinical-review", default="PENDING")
    s.add_argument("--version", default="v0.1"); s.set_defaults(func=cmd_scan)

    q = sub.add_parser("qc"); q.add_argument("--min-size", type=int, default=256)
    q.add_argument("--lum-min", type=float, default=0.15); q.add_argument("--lum-max", type=float, default=0.90)
    q.add_argument("--contrast-min", type=float, default=0.03); q.set_defaults(func=cmd_qc)

    v = sub.add_parser("validate"); v.add_argument("--per-condition", type=int, default=8); v.set_defaults(func=cmd_validate)
    sub.add_parser("sources").set_defaults(func=cmd_sources)
    pr = sub.add_parser("prune"); pr.add_argument("--source", required=True); pr.set_defaults(func=cmd_prune)
    pv = sub.add_parser("provenance"); pv.add_argument("--ethics-id"); pv.add_argument("--consent-id")
    pv.add_argument("--source"); pv.set_defaults(func=cmd_provenance)
    sub.add_parser("contacts").set_defaults(func=cmd_contacts)
    r = sub.add_parser("report"); r.add_argument("--per-condition", type=int, default=8); r.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
