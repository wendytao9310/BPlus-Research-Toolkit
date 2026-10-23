#!/usr/bin/env python
"""UIBVFED 快速起步 fetcher（**只在 CC-BY/CC0 且公开可下载时才下载**）。

    # 1) 先看清单与授权（默认行为，不下载任何东西）
    python scripts/fetch_uibvfed.py --list

    # 2) 下载"快速起步"小集（zenodo.399066，约 2.6 MB，CC-BY-4.0）
    python scripts/fetch_uibvfed.py --download --record 399066

    # 3) 下载主集（UIBVFED.rar，约 1.7 GB）
    python scripts/fetch_uibvfed.py --download --record uibvfed

    # 4) 解压后按 3 条件映射（happy→positive / neutral→neutral / sad→negative）
    python scripts/fetch_uibvfed.py --map

设计纪律（对应任务 §2/§5/§37）：
  * 只有 license 属于 {cc-by-4.0, cc-by-sa-4.0, cc0} 且 access_right=open 才允许下载；
  * 下载后校验 API 给出的 checksum（md5）；
  * 不做登录、不绕验证码、不使用第三方镜像的"再许可"声明；
  * 下载的是**虚拟面孔**（3D 渲染），登记为 VIRTUAL_FACE，必须按独立刺激类型验证（§40）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ZENODO_API = "https://zenodo.org/api/records"
ALLOWED_LICENCES = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "cc0"}
UA = "BPlusStimulusFetcher/0.1 (research; contact: local)"

# 本脚本内置三个已核实记录（2026-09-22 通过 Zenodo API 实查）
RECORDS = {
    "quickstart": {"record": "399066", "doi": "10.5281/zenodo.399066",
                   "label": "Images for 'Evaluating the Sensitivity to Virtual Characters'（≈2.6 MB）"},
    "uibvfed": {"record": "10.1371/journal.pone.0231266", "doi": "10.1371/journal.pone.0231266",
                "label": "UIBVFED: Virtual facial expression dataset（UIBVFED.rar ≈1.7 GB）"},
    "physical": {"record": "10793613", "doi": "10.5281/zenodo.10793613",
                 "label": "UIBVFED Physical States（DATASET.zip ≈3.2 GB）"},
}

# ── 标签映射分两层，避免"随便分类" ──────────────────────────────────────────
# ① 核心映射：语义无歧义，脚本可直接映射
CORE_LABEL_MAP = {
    "happy": "positive", "happiness": "positive", "smile": "positive", "joy": "positive",
    "neutral": "neutral", "calm": "neutral", "peaceful": "neutral",   # peaceful = 低唤醒平静
    "sad": "negative", "sadness": "negative", "anger": "negative", "angry": "negative",
    "disgust": "negative", "fear": "negative", "fearful": "negative",
}
# ② 模糊映射：**默认不映射**，必须看 contact sheet 后由人决定（--include-ambiguous 才临时映射）
AMBIGUOUS_LABEL_MAP = {
    "smirk": "positive",          # 得意/讥笑：正性？还是带敌意的负性？→ 人工判定
    "p2bcool": "positive",        # "playing it cool"：社交性表达，非基本情绪
    "2good2btrue": "positive",    # "too good to be true"：正性但含怀疑色彩
    "suspicious": "negative",     # 社交怀疑：负性？还是中性警觉？
    "vicious": "negative",        # 凶狠：负性，但与恐惧/悲伤性质不同
}
LABEL_MAP = {**CORE_LABEL_MAP, **AMBIGUOUS_LABEL_MAP}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def describe(record: str) -> dict:
    """返回记录元数据（含授权、文件、校验和）。record 传数字 id 或 DOI。"""
    if record.startswith("10."):
        data = fetch_json(f"https://zenodo.org/api/records?q=doi:%22{record}%22&size=1")
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            raise SystemExit(f"Zenodo 未找到 DOI {record}")
        return hits[0]
    return fetch_json(f"{ZENODO_API}/{record}")


def licence_of(rec: dict) -> str:
    lic = (rec.get("metadata", {}).get("license") or {})
    lic = lic.get("id") if isinstance(lic, dict) else lic
    return (lic or "").lower()


def check_download_allowed(rec: dict) -> tuple[bool, str]:
    lic = licence_of(rec)
    access = (rec.get("metadata", {}).get("access_right") or "").lower()
    if lic not in ALLOWED_LICENCES:
        return False, f"授权 {lic or '未知'} 不在允许集合 {sorted(ALLOWED_LICENCES)} → 不下载"
    if access and access != "open":
        return False, f"访问级别 {access} 非 open → 不下载"
    return True, f"授权 {lic}，access={access or 'open'} ✅"


def cmd_list(args) -> int:
    print(f"{'别名':<12}{'DOI':<40}{'授权':<14}{'文件数':>6}{'总量 MB':>12}  说明")
    for key, meta in RECORDS.items():
        try:
            rec = describe(meta["record"])
        except Exception as exc:                       # pragma: no cover - 网络相关
            print(f"{key:<12}{meta['doi']:<40}{'查询失败':<14}{'-':>6}{'-':>12}  {exc}")
            continue
        files = rec.get("files", [])
        total = sum(f.get("size", 0) for f in files) / 1e6
        ok, why = check_download_allowed(rec)
        print(f"{key:<12}{rec.get('doi', meta['doi']):<40}{licence_of(rec):<14}{len(files):>6}{total:>12.1f}  {meta['label']}")
        print(f"             └─ {'可下载' if ok else '禁止下载'}：{why}")
        for f in files[:6]:
            print(f"                - {f.get('key')}  ({f.get('size',0)/1e6:.2f} MB)")
    print("\n提示：Plus-Light（DOI 10.1371/journal.pone.0287006）总量约 33.6 GB，"
          "未纳入快速起步；如需请自行按同样的授权检查流程处理。")
    return 0


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh, length=1 << 20)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_download(args) -> int:
    meta = RECORDS[args.record]
    rec = describe(meta["record"])
    ok, why = check_download_allowed(rec)
    print(f"记录：{rec.get('metadata',{}).get('title','')[:80]}\n授权检查：{why}")
    if not ok:
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in rec.get("files", []):
        key = f.get("key")
        url = (f.get("links") or {}).get("self")
        if not key or not url:
            continue
        if args.max_mb and f.get("size", 0) / 1e6 > args.max_mb:
            print(f"  跳过（超过 --max-mb={args.max_mb}）：{key}（{f.get('size',0)/1e6:.1f} MB）")
            continue
        dest = out / key
        print(f"  下载 {key}（{f.get('size',0)/1e6:.2f} MB）…")
        _download(url, dest)
        want = (f.get("checksum") or "").replace("md5:", "")
        if want:
            got = _md5(dest)
            status = "✅" if got == want else "❌ 校验失败"
            print(f"     checksum {status}（md5 {got[:12]}…）")
            if got != want:
                return 3
    print(f"\n完成 → {out}\n注意：下载的是**虚拟面孔**，登记为 VIRTUAL_FACE；"
          "使用必须署名（见 QUICKSTART_UIBVFED.md）。")
    return 0


def classify(name: str, *, include_ambiguous: bool = False) -> str | None:
    low = name.lower()
    table = LABEL_MAP if include_ambiguous else CORE_LABEL_MAP
    for label in sorted(table, key=len, reverse=True):
        if label in low:
            return table[label]
    return None


def is_ambiguous(name: str) -> bool:
    low = name.lower()
    return any(label in low for label in AMBIGUOUS_LABEL_MAP)


def cmd_map(args) -> int:
    src = Path(args.src)
    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    unmapped, ambiguous_used = [], []
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    for p in sorted(src.rglob("*")):
        if p.suffix.lower() not in exts:
            continue
        cond = (classify(p.name, include_ambiguous=args.include_ambiguous)
                or classify(str(p.relative_to(src)), include_ambiguous=args.include_ambiguous))
        if not cond:
            unmapped.append(p.name + ("（模糊标签，需人工判定）" if is_ambiguous(p.name) else ""))
            continue
        if is_ambiguous(p.name):
            ambiguous_used.append(f"{p.name} → {cond}")
        counts[cond] += 1
        shutil.copy2(p, dst / f"{cond}_{counts[cond]:03d}{p.suffix.lower()}")
    print(f"映射完成：positive={counts['positive']} neutral={counts['neutral']} negative={counts['negative']}")
    if unmapped:
        print(f"⚠️ 未能自动映射 {len(unmapped)} 个：{unmapped[:8]}")
    if ambiguous_used:
        (dst / "MAPPING_REVIEW_NEEDED.md").write_text(
            "# 模糊标签映射待人工确认\n\n"
            "下列文件按**临时**映射归入条件，必须由研究团队看完 contact sheet 后确认或改判：\n\n"
            + "\n".join(f"- {x}" for x in ambiguous_used)
            + "\n\n> 若改判：把文件移到对应条件前缀后重新 scan（并删除旧记录）。\n",
            encoding="utf-8")
        print(f"⚠️ {len(ambiguous_used)} 个模糊标签已临时映射 → {dst/'MAPPING_REVIEW_NEEDED.md'}（必须人工确认）")
    print(f"→ {dst}\n下一步：\n"
          f"  python scripts/emotion_library.py scan --dir {dst} --source UIBVFED_QUICKSTART \\\n"
          f"      --age-suitability PENDING --cultural-suitability PENDING "
          f"--ethics-status PENDING --clinical-review PENDING --version uibvfed-v1")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UIBVFED 快速起步 fetcher")
    ap.add_argument("--list", action="store_true", help="只列清单与授权（默认）")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--record", default="quickstart", choices=sorted(RECORDS))
    ap.add_argument("--out", default="stimuli/emotion/raw/uibvfed")
    ap.add_argument("--max-mb", type=float, default=0, help="单文件大小上限（MB，0=不限）")
    ap.add_argument("--map", action="store_true", help="把已解压文件按条件映射到 *_mapped/")
    ap.add_argument("--src", default="stimuli/emotion/raw/uibvfed")
    ap.add_argument("--dst", default="stimuli/emotion/raw/uibvfed_mapped")
    ap.add_argument("--include-ambiguous", action="store_true",
                    help="同时映射模糊标签（smirk/P2Bcool/2good2btrue/suspicious/vicious）并生成待确认清单")
    args = ap.parse_args(argv)
    if args.map:
        return cmd_map(args)
    if args.download:
        return cmd_download(args)
    return cmd_list(args)


if __name__ == "__main__":
    raise SystemExit(main())
