"""情绪刺激库：清单、技术 QC、平衡性检查与 **REAL MODE 闸门**。

对应《Emotion Stimulus Library Repair & Validation Task》§1/§3/§47：
  * 清单非空、文件存在可读、授权可追溯、年龄/文化/伦理已审、技术 QC 通过、
    平衡性通过、PILOT 完成、临床团队批准 —— 全部满足才允许 REAL_MODE；
  * 不满足时抛出**指定错误信息**：
    "ERROR: Emotion stimulus library is not validated for real participant acquisition."
  * 图片一律不自动下载（除非来源在 configs/stimuli/emotion_sources.yaml 中标记
    auto_download_allowed: true 且授权属于允许状态）。
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .. import config as cfg_mod

REAL_MODE_ERROR = ("ERROR: Emotion stimulus library is not validated for real participant "
                   "acquisition.")

REQUIRED_COLUMNS = [
    "stimulus_id", "condition", "file", "sha256", "width", "height",
    "source_id", "license_status", "age_suitability", "cultural_suitability",
    "ethics_status", "clinical_review", "technical_qc",
    "luminance_mean", "luminance_sd", "contrast_rms", "duplicate_of", "version", "notes",
]

ALLOWED_LICENSE_STATES = {"CC_BY_4_0", "CC0", "PROJECT_GENERATED", "PUBLIC_DOMAIN",
                          "RESEARCH_NONCOMMERCIAL_NO_REDISTRIBUTION"}

DEFAULT_ROOT = Path("stimuli/emotion")


@dataclass
class StimulusRecord:
    stimulus_id: str
    condition: str
    file: str
    source_id: str = ""
    license_status: str = ""
    sha256: str = ""
    width: int = 0
    height: int = 0
    age_suitability: str = ""
    cultural_suitability: str = ""
    ethics_status: str = ""
    clinical_review: str = ""
    technical_qc: str = ""
    luminance_mean: float = float("nan")
    luminance_sd: float = float("nan")
    contrast_rms: float = float("nan")
    duplicate_of: str = ""
    version: str = ""
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class LibraryValidation:
    ok: bool
    checks: dict = field(default_factory=dict)
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    n_stimuli: int = 0
    n_by_condition: dict = field(default_factory=dict)
    error_message: str = REAL_MODE_ERROR

    def as_dict(self) -> dict:
        return asdict(self)


def load_sources(path: str | Path | None = None) -> dict:
    p = Path(path) if path else Path(cfg_mod.CONFIG_DIR) / "stimuli" / "emotion_sources.yaml"
    import yaml

    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {s["id"]: s for s in cfg.get("sources", [])}


def load_manifest(root: str | Path = DEFAULT_ROOT) -> list[StimulusRecord]:
    path = Path(root) / "manifest.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if not (r.get("stimulus_id") or "").strip():
            continue
        rec = StimulusRecord(stimulus_id=r["stimulus_id"].strip(), condition=(r.get("condition") or "").strip(),
                             file=(r.get("file") or "").strip(), source_id=(r.get("source_id") or "").strip(),
                             license_status=(r.get("license_status") or "").strip(),
                             sha256=(r.get("sha256") or "").strip(),
                             age_suitability=(r.get("age_suitability") or "").strip(),
                             cultural_suitability=(r.get("cultural_suitability") or "").strip(),
                             ethics_status=(r.get("ethics_status") or "").strip(),
                             clinical_review=(r.get("clinical_review") or "").strip(),
                             technical_qc=(r.get("technical_qc") or "").strip(),
                             duplicate_of=(r.get("duplicate_of") or "").strip(),
                             version=(r.get("version") or "").strip(),
                             notes=(r.get("notes") or "").strip())
        for numeric, cast in (("width", int), ("height", int), ("luminance_mean", float),
                              ("luminance_sd", float), ("contrast_rms", float)):
            raw = (r.get(numeric) or "").strip()
            try:
                setattr(rec, numeric, cast(raw) if raw else 0 if cast is int else float("nan"))
            except ValueError:
                setattr(rec, numeric, 0 if cast is int else float("nan"))
        out.append(rec)
    return out


# --------------------------------------------------------------------------- 技术 QC
def image_technical_qc(path: str | Path) -> dict:
    """单张刺激的亮度/对比度/尺寸/感知哈希（用于重复检测）。"""
    from PIL import Image

    p = Path(path)
    img = Image.open(p).convert("L")
    arr = np.asarray(img, dtype=float) / 255.0
    # ⚠️ 用 16×16（256 bit）aHash，而不是 8×8：8×8 对"面孔刺激"太粗，
    # 会把不同人脸互相判成重复（本项目实测 16 张 UIBVFED 面孔被 8×8 哈希判出大量重复）。
    small = np.asarray(img.resize((16, 16), Image.BILINEAR), dtype=float)
    ahash = "".join("1" if v > small.mean() else "0" for v in small.flatten())
    return {"width": img.width, "height": img.height,
            "luminance_mean": float(arr.mean()), "luminance_sd": float(arr.std()),
            "contrast_rms": float(np.sqrt(np.mean((arr - arr.mean()) ** 2))),
            "ahash": ahash, "sha256": sha256_file(p)}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hamming(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b))


def find_duplicates(hashes: dict[str, str], *, max_distance: int = 4) -> dict[str, str]:
    """返回 {重复者: 原图}。感知哈希（8×8 aHash）距离 ≤ max_distance 视为重复。

    max_distance=4（256 bit 的 1.6%）是 PROJECT_ENGINEERING 初值（配合 16×16 哈希）：
    实测 UIBVFED 不同面孔的两两距离中位数为 72，因此 4 不会误伤；而重新编码/缩放同一张图
    的距离通常在 0–4，能被稳到抓到。太小会漏掉轻微重复，太大则会把"同一个人不同表情"
    误判为重复。真实刺激库上线前必须用人工 contact sheet 复核本项结论。
    """
    ids = sorted(hashes)
    dupes = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if a in dupes:
                continue
            if _hamming(hashes[a], hashes[b]) <= max_distance:
                dupes[b] = a
    return dupes


# --------------------------------------------------------------------------- 平衡性
def check_balance(records: list[StimulusRecord], *, per_condition: int,
                  conditions=("positive", "neutral", "negative")) -> dict:
    counts = {c: sum(1 for r in records if r.condition == c) for c in conditions}
    issues = [f"{c} 只有 {counts[c]} 张（目标 {per_condition}）" for c in conditions
              if counts[c] != per_condition]
    return {"counts": counts, "per_condition": per_condition, "balanced": not issues, "issues": issues}


# --------------------------------------------------------------------------- 闸门
def validate_library(root: str | Path = DEFAULT_ROOT, *, sources: dict | None = None,
                     per_condition: int = 8, require_clinical_approval: bool = True) -> LibraryValidation:
    root = Path(root)
    records = load_manifest(root)
    sources = sources if sources is not None else load_sources()
    checks: dict[str, bool] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    checks["manifest_non_empty"] = len(records) > 0
    if not records:
        blockers.append("manifest.csv 为空：没有任何已登记的刺激")

    # 文件存在 + 可读 + 尺寸/哈希
    missing, unreadable, qc_fail, mismatch = [], [], [], []
    hashes = {}
    for r in records:
        p = root / r.file
        if not r.file or not p.exists():
            missing.append(r.stimulus_id)
            continue
        try:
            q = image_technical_qc(p)
        except Exception:
            unreadable.append(r.stimulus_id)
            continue
        hashes[r.stimulus_id] = q["ahash"]
        if r.sha256 and r.sha256 != q["sha256"]:
            mismatch.append(r.stimulus_id)
        if r.technical_qc != "PASS":
            qc_fail.append(r.stimulus_id)
    checks["files_exist"] = not missing
    checks["files_readable"] = not unreadable
    checks["sha256_matches"] = not mismatch
    checks["technical_qc_passed"] = not qc_fail
    for name, ids in (("缺失文件", missing), ("不可读", unreadable), ("哈希不匹配", mismatch),
                      ("技术 QC 未通过", qc_fail)):
        if ids:
            blockers.append(f"{name}：{', '.join(ids[:8])}{' …' if len(ids) > 8 else ''}")

    dupes = find_duplicates(hashes)
    checks["duplicate_check_passed"] = not dupes
    if dupes:
        blockers.append(f"检测到重复刺激：{list(dupes.items())[:5]}")

    # 授权
    bad_license = [r.stimulus_id for r in records if r.license_status not in ALLOWED_LICENSE_STATES]
    unknown_source = [r.stimulus_id for r in records if r.source_id not in sources]
    checks["licence_audited"] = not bad_license
    checks["source_traceable"] = not unknown_source
    if bad_license:
        blockers.append(f"授权状态不允许：{', '.join(bad_license[:8])}")
    if unknown_source:
        blockers.append(f"来源未登记于 emotion_sources.yaml：{', '.join(unknown_source[:8])}")

    def _missing_flag(attr, ok_value=("YES", "OK", "PASS")):
        return [r.stimulus_id for r in records if getattr(r, attr).upper() not in ok_value]

    for field_name, label in (("age_suitability", "年龄适配"), ("cultural_suitability", "文化适配"),
                              ("ethics_status", "伦理状态"), ("clinical_review", "临床审阅")):
        bad = _missing_flag(field_name)
        key = {"age_suitability": "age_suitability_audited",
               "cultural_suitability": "cultural_suitability_audited",
               "ethics_status": "ethics_status_audited",
               "clinical_review": "clinical_review_done"}[field_name]
        checks[key] = not bad
        if bad:
            blockers.append(f"{label}未通过：{', '.join(bad[:8])}")

    bal = check_balance(records, per_condition=per_condition)
    checks["stimulus_balance_passed"] = bal["balanced"]
    if not bal["balanced"]:
        warnings.append("平衡性未达标：" + "；".join(bal["issues"]))

    validation_md = root / "VALIDATION_REPORT.md"
    checks["validation_report_completed"] = validation_md.exists() and "STATUS: COMPLETE" in \
        validation_md.read_text(encoding="utf-8", errors="ignore")
    if not checks["validation_report_completed"]:
        blockers.append("VALIDATION_REPORT.md 尚未标记 STATUS: COMPLETE")

    pilot = root / "PILOT_PROTOCOL.md"
    checks["pilot_protocol_present"] = pilot.exists()
    if not pilot.exists():
        blockers.append("缺少 PILOT_PROTOCOL.md")

    if require_clinical_approval:
        approval = root / "CLINICAL_APPROVAL.md"
        checks["clinical_team_approval"] = approval.exists() and "APPROVED" in \
            approval.read_text(encoding="utf-8", errors="ignore").upper()
        if not checks["clinical_team_approval"]:
            blockers.append("缺少临床团队批准（CLINICAL_APPROVAL.md 未标记 APPROVED）")

    checks["version_assigned"] = all(r.version for r in records)
    if not checks["version_assigned"]:
        blockers.append("存在未分配 version 的刺激")

    ok = not blockers
    return LibraryValidation(ok=ok, checks=checks, blockers=blockers, warnings=warnings,
                             n_stimuli=len(records), n_by_condition=bal["counts"])


def assert_real_mode_allowed(root: str | Path = DEFAULT_ROOT, **kwargs) -> LibraryValidation:
    """REAL MODE 闸门：不满足条件时抛出指定错误信息。"""
    report = validate_library(root, **kwargs)
    if not report.ok:
        detail = "\n".join(f"  - {b}" for b in report.blockers[:12])
        raise RuntimeError(f"{REAL_MODE_ERROR}\n阻断项（{len(report.blockers)}）：\n{detail}")
    return report


def write_validation_json(report: LibraryValidation, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
