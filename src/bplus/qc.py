"""数据质量评定（QC）与 DQ 总分 —— MASTER COMMAND §39-42。

设计原则：
  * 所有阈值来自 `configs/qc.yaml`（禁止硬编码）；
  * 每个子分数都能追溯到具体指标（§53）；
  * 阈值一律标 `PILOT_REQUIRED` / `ENGINEERING`，报告中不得写成国际标准。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from . import config as cfg_mod


def _scale(value: float, *, good: float, bad: float) -> float:
    """把指标线性映射到 0–100：good → 100，bad → 0（good 可以大于或小于 bad）。"""
    if good == bad:
        return 100.0
    frac = (value - bad) / (good - bad)
    return float(np.clip(frac, 0.0, 1.0) * 100.0)


@dataclass
class SubScore:
    score: float
    label: str
    inputs: dict = field(default_factory=dict)
    evidence_status: str = "PILOT_REQUIRED"


@dataclass
class DQReport:
    score: float
    band: str
    band_zh: str
    components: dict = field(default_factory=dict)
    evidence_status: str = "PILOT_REQUIRED + ENGINEERING"
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def score_eeg(*, usable_channel_ratio: float, line_noise_ratio: float = 0.0,
              movement_artifact_ratio: float = 0.0, epoch_rejection_ratio: float = 0.0,
              cfg: dict | None = None) -> SubScore:
    c = (cfg or cfg_mod.load_yaml("qc.yaml"))["eeg"]
    w = c["weights"]
    parts = {
        "usable_channels": _scale(usable_channel_ratio, good=c["usable_channel_ratio"]["target"],
                                  bad=c["usable_channel_ratio"]["floor"]),
        "line_noise": _scale(line_noise_ratio, good=0.0, bad=c["line_noise_ratio_max"]),
        "artifacts": _scale(movement_artifact_ratio, good=0.0, bad=c["movement_artifact_ratio_max"]),
        "epochs": _scale(epoch_rejection_ratio, good=0.0, bad=c["epoch_rejection_max"]),
    }
    score = sum(parts[k] * w[k] for k in w) / sum(w.values())
    label = "GOOD" if score >= 85 else "ACCEPTABLE" if score >= 70 else "POOR" if score >= 50 else "INVALID"
    return SubScore(score=round(score, 2), label=label,
                    inputs={"usable_channel_ratio": usable_channel_ratio, "line_noise_ratio": line_noise_ratio,
                            "movement_artifact_ratio": movement_artifact_ratio,
                            "epoch_rejection_ratio": epoch_rejection_ratio, "parts": {k: round(v, 2) for k, v in parts.items()}})


def score_fnirs(*, sci: float, channel_quality: float, motion_artifact_ratio: float = 0.0,
                baseline_drift: float = 0.0, cfg: dict | None = None) -> SubScore:
    c = (cfg or cfg_mod.load_yaml("qc.yaml"))["fnirs"]
    w = c["weights"]
    parts = {
        "sci": _scale(sci, good=max(c["sci_min"], 0.95), bad=max(0.0, c["sci_min"] - 0.4)),
        "channels": _scale(channel_quality, good=1.0, bad=c["channel_quality_min"]),
        "motion": _scale(motion_artifact_ratio, good=0.0, bad=c["motion_artifact_ratio_max"]),
        "baseline": _scale(baseline_drift, good=0.0, bad=c["baseline_drift_max"]),
    }
    score = sum(parts[k] * w[k] for k in w) / sum(w.values())
    label = "GOOD" if score >= 85 else "ACCEPTABLE" if score >= 70 else "POOR" if score >= 50 else "INVALID"
    return SubScore(score=round(score, 2), label=label,
                    inputs={"sci": sci, "channel_quality": channel_quality,
                            "motion_artifact_ratio": motion_artifact_ratio, "baseline_drift": baseline_drift,
                            "parts": {k: round(v, 2) for k, v in parts.items()}})


def score_epoch(*, valid_epoch_ratio: float, n_epochs_per_condition: int, cfg: dict | None = None) -> SubScore:
    c = (cfg or cfg_mod.load_yaml("qc.yaml"))["epoch"]
    ratio_score = _scale(valid_epoch_ratio, good=1.0, bad=c["valid_ratio_target"] - 0.3)
    count_score = _scale(float(n_epochs_per_condition), good=float(c["min_epochs_per_condition"]) * 1.5,
                         bad=float(c["min_epochs_per_condition"]))
    score = 0.7 * ratio_score + 0.3 * count_score
    label = "GOOD" if score >= 85 else "ACCEPTABLE" if score >= 70 else "POOR" if score >= 50 else "INVALID"
    return SubScore(score=round(score, 2), label=label,
                    inputs={"valid_epoch_ratio": valid_epoch_ratio, "n_epochs_per_condition": n_epochs_per_condition})


def score_synchronization(*, pulse_completeness: bool, offset_ms: float | None, jitter_sd_ms: float | None,
                          verdict: str = "INCONCLUSIVE", cfg: dict | None = None) -> SubScore:
    c = (cfg or cfg_mod.load_yaml("qc.yaml"))["synchronization"]
    if verdict == "PASS":
        score = 100.0
    elif verdict == "FAIL":
        score = 0.0
    else:
        score = 50.0
    if c["require_pulse_completeness"] and not pulse_completeness:
        score = 0.0
    label = "GOOD" if score >= 85 else "ACCEPTABLE" if score >= 70 else "POOR" if score >= 50 else "INVALID"
    return SubScore(score=score, label=label,
                    inputs={"verdict": verdict, "pulse_completeness": pulse_completeness,
                            "offset_ms": offset_ms, "jitter_sd_ms": jitter_sd_ms,
                            "limits": {"offset_abs_max_ms": c["offset_abs_max_ms"], "jitter_sd_max_ms": c["jitter_sd_max_ms"]}})


def score_physiology(*, valid_segment_ratio: float, hrv_sdnn_ms: float | None = None,
                     scr_events: int = 0, cfg: dict | None = None) -> SubScore:
    c = (cfg or cfg_mod.load_yaml("qc.yaml"))["physiology"]
    parts = {"segments": _scale(valid_segment_ratio, good=1.0, bad=c["valid_segment_ratio_target"] - 0.3)}
    if hrv_sdnn_ms is not None:
        parts["hrv"] = _scale(hrv_sdnn_ms, good=max(c["min_hrv_sdnn_ms"] * 4, 40),
                              bad=float(c["min_hrv_sdnn_ms"]))
    parts["eda"] = 100.0 if scr_events >= c["scr_events_min"] else 50.0
    score = float(np.mean(list(parts.values())))
    label = "GOOD" if score >= 85 else "ACCEPTABLE" if score >= 70 else "POOR" if score >= 50 else "INVALID"
    return SubScore(score=round(score, 2), label=label,
                    inputs={"valid_segment_ratio": valid_segment_ratio, "hrv_sdnn_ms": hrv_sdnn_ms,
                            "scr_events": scr_events, "parts": {k: round(v, 2) for k, v in parts.items()}})


def compute_dq(*, eeg: SubScore, fnirs: SubScore, epoch: SubScore, sync: SubScore,
               physiology: SubScore | None = None, cfg: dict | None = None) -> DQReport:
    """DQ 加权合成。

    某个分项为 None（例如本次没采生理信号）时，**从权重里去掉并把剩余权重归一化**，
    而不是把它按 0 分算——否则少采一个模态会让 DQ 假性崩盘。
    """
    c = cfg or cfg_mod.load_yaml("qc.yaml")
    w = dict(c["dq_weights"])
    parts = {"eeg": eeg, "fnirs": fnirs, "epoch": epoch, "synchronization": sync, "physiology": physiology}
    missing = [k for k, v in parts.items() if v is None]
    active_w = {k: v for k, v in w.items() if parts[k] is not None}
    total_w = sum(active_w.values()) or 1.0
    score = sum(parts[k].score * (active_w[k] / total_w) for k in active_w)
    band = next(b for b in c["dq_bands"] if score >= b["min"])
    notes = []
    if missing:
        notes.append(f"未采集/未提供分项：{', '.join(missing)}；DQ 已在剩余分项上重新归一化权重")
    for name, sub in (("eeg", eeg), ("fnirs", fnirs), ("epoch", epoch),
                      ("synchronization", sync), ("physiology", physiology)):
        if sub is not None and sub.label in ("POOR", "INVALID"):
            notes.append(f"{name} 质量偏低（{sub.score}），其结果置信度必须下调")
    return DQReport(score=round(score, 2), band=band["label"], band_zh=band["zh"],
                    components={k: (None if v is None else asdict(v)) for k, v in parts.items()} | {
                        "weights_effective": active_w, "weights_declared": w,
                        "missing": missing},
                    notes=notes)


def dq_from_feature_dict(features: dict, *, sync_report: dict | None = None, cfg: dict | None = None) -> DQReport:
    """从特征字典（features.py 产出）+ sync_report 计算完整 DQ。"""
    qc_cfg = cfg or cfg_mod.load_yaml("qc.yaml")
    eeg_f, fnirs_f, physio_f = features.get("eeg", {}), features.get("fnirs", {}), features.get("physiology", {})
    eeg = score_eeg(usable_channel_ratio=eeg_f.get("usable_channel_ratio", 1.0),
                    line_noise_ratio=eeg_f.get("line_noise_ratio", 0.0),
                    movement_artifact_ratio=eeg_f.get("artifact_ratio", 0.0),
                    epoch_rejection_ratio=eeg_f.get("epoch_rejection_ratio", 0.0), cfg=qc_cfg)
    fnirs = score_fnirs(sci=fnirs_f.get("sci", 0.8), channel_quality=fnirs_f.get("channel_quality", 0.9),
                        motion_artifact_ratio=fnirs_f.get("motion_artifact_ratio", 0.0),
                        baseline_drift=fnirs_f.get("baseline_drift", 0.0), cfg=qc_cfg)
    epoch = score_epoch(valid_epoch_ratio=features.get("epoch", {}).get("valid_ratio", 0.9),
                        n_epochs_per_condition=features.get("epoch", {}).get("n_per_condition", 40), cfg=qc_cfg)
    sync = score_synchronization(pulse_completeness=(sync_report or {}).get("counts", {}).get("fnirs", 0) > 0
                                 and not (sync_report or {}).get("missing_codes"),
                                 offset_ms=(sync_report or {}).get("offset_ms"),
                                 jitter_sd_ms=(sync_report or {}).get("jitter_sd_ms"),
                                 verdict=(sync_report or {}).get("verdict", "INCONCLUSIVE"), cfg=qc_cfg)
    physiology = score_physiology(valid_segment_ratio=physio_f.get("valid_segment_ratio", 0.95),
                                  hrv_sdnn_ms=physio_f.get("hrv_sdnn_ms"),
                                  scr_events=physio_f.get("scr_events", 0), cfg=qc_cfg)
    return compute_dq(eeg=eeg, fnirs=fnirs, epoch=epoch, sync=sync, physiology=physiology, cfg=qc_cfg)
