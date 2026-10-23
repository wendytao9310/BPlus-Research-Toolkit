"""Auditable MMN/VFT analysis workflow for BPlus research reports."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def analyze_mmn_epochs(standard_epochs, deviant_epochs, times_ms, channel_names,
                       *, roi=("Fz", "Cz"), window_ms=(100.0, 250.0), min_epochs=10) -> dict[str, Any]:
    """Score the deviant-minus-standard MMN from baseline-corrected epochs.

    Arrays are epochs x channels x samples, in microvolts. This function does
    not guess vendor channel/event mappings; those remain explicit import work.
    """
    standard = np.asarray(standard_epochs, dtype=float)
    deviant = np.asarray(deviant_epochs, dtype=float)
    times = np.asarray(times_ms, dtype=float)
    if standard.ndim != 3 or deviant.ndim != 3 or standard.shape[1:] != deviant.shape[1:]:
        raise ValueError("MMN 数据必须为 epochs × channels × samples，且两类形状一致")
    if standard.shape[2] != len(times) or standard.shape[1] != len(channel_names):
        raise ValueError("时间轴或通道名与 MMN 数据形状不一致")
    indices = [channel_names.index(name) for name in roi if name in channel_names]
    if not indices:
        raise ValueError(f"未找到 MMN ROI 通道：{', '.join(roi)}")
    baseline = (times >= -100.0) & (times <= 0.0)
    window = (times >= window_ms[0]) & (times <= window_ms[1])
    if not baseline.any() or not window.any():
        raise ValueError("MMN 时间轴不包含基线或分析窗")

    def corrected_mean(data):
        corrected = data - data[:, :, baseline].mean(axis=2, keepdims=True)
        return corrected.mean(axis=0)

    difference = corrected_mean(deviant) - corrected_mean(standard)
    roi_wave = difference[indices].mean(axis=0)
    segment = roi_wave[window]
    segment_times = times[window]
    peak_index = int(np.argmin(segment))
    status = "PASS" if min(len(standard), len(deviant)) >= min_epochs else "QC_FAILED"
    notes = [] if status == "PASS" else [f"有效试次数不足：标准 {len(standard)}，偏差 {len(deviant)}"]
    return {
        "features": {
            "mmn_amplitude_uv": float(segment[peak_index]),
            "mmn_amplitude_abs_uv": float(abs(segment[peak_index])),
            "mmn_latency_ms": float(segment_times[peak_index]),
        },
        "qc": {"status": status, "n_standard": len(standard), "n_deviant": len(deviant),
               "roi_channels": [channel_names[i] for i in indices], "window_ms": list(window_ms),
               "notes": notes},
    }


def write_vft_scoring_template(path: str | Path, prompts=("动物", "水果", "交通工具", "职业")) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["block", "prompt", "transcript", "valid_words",
                                                         "repetitions", "intrusions", "reviewer"])
        writer.writeheader()
        for index, prompt in enumerate(prompts, 1):
            writer.writerow({"block": index, "prompt": prompt, "transcript": "", "valid_words": "",
                             "repetitions": "", "intrusions": "", "reviewer": ""})
    return target


def read_vft_scoring(path: str | Path) -> dict[str, Any]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"block", "prompt", "transcript", "valid_words", "repetitions", "intrusions", "reviewer"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("VFT 计分表字段不完整")
    totals = {key: sum(int(row.get(key) or 0) for row in rows)
              for key in ("valid_words", "repetitions", "intrusions")}
    reviewers = sorted({row["reviewer"].strip() for row in rows if row.get("reviewer", "").strip()})
    return {"status": "SCORED" if reviewers else "PENDING_REVIEW", "blocks": rows,
            "totals": totals, "reviewers": reviewers}


def analyze_vft_hbo(hbo, fs: float, *, task_windows, rest_windows, channel_names=None,
                     min_duration_s=60.0) -> dict[str, Any]:
    """Compute channel-wise VFT task-minus-rest HbO change in micromolar units."""
    data = np.asarray(hbo, dtype=float)
    if data.ndim == 1:
        data = data[None, :]
    if data.ndim != 2 or fs <= 0:
        raise ValueError("VFT HbO 必须为 channels × samples，且采样率大于 0")
    names = list(channel_names or [f"CH{i + 1}" for i in range(data.shape[0])])
    if len(names) != data.shape[0]:
        raise ValueError("VFT 通道名数量与数据不一致")

    def window_mean(signal, windows):
        values = []
        for onset, duration in windows:
            left, right = max(0, int(onset * fs)), min(len(signal), int((onset + duration) * fs))
            if right > left:
                values.append(float(np.mean(signal[left:right])))
        return float(np.mean(values)) if values else float("nan")

    deltas = np.array([window_mean(row, task_windows) - window_mean(row, rest_windows) for row in data])
    finite = np.isfinite(deltas)
    status = "PASS" if finite.any() and data.shape[1] / fs >= min_duration_s else "QC_FAILED"
    return {
        "features": {"vft_hbo_delta_um": float(np.nanmean(deltas)) if finite.any() else None,
                     "vft_hbo_block_sd": float(np.nanstd(deltas)) if finite.any() else None},
        "qc": {"status": status, "duration_s": data.shape[1] / fs,
               "usable_channel_ratio": float(finite.mean()),
               "channel_deltas_um": dict(zip(names, [float(x) for x in deltas])),
               "notes": [] if status == "PASS" else ["有效时长或通道不足"]},
    }


def build_analysis_package(participant_id: str, session_id: str, *, age: int | None = None,
                           mmn=None, vft=None, vft_scoring=None) -> dict[str, Any]:
    features = {"eeg": {}, "fnirs": {}, "vft": {}, "nback": {}, "nvc": {}, "emotion": {},
                "recovery": {}, "eye": {}, "clinical": {}}
    sources = {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")}
    qc_items = []
    if mmn:
        features["eeg"].update(mmn.get("features", {})); qc_items.append(mmn.get("qc", {}))
        sources["eeg"] = {"status": "PILOT", "format": "BPlus MMN epoch analysis"}
    if vft:
        features["fnirs"].update(vft.get("features", {})); qc_items.append(vft.get("qc", {}))
        sources["fnirs"] = {"status": "PILOT", "format": "BPlus VFT HbO analysis"}
    if vft_scoring:
        features["vft"].update(vft_scoring.get("totals", {}))
        sources["behavior"] = {"status": "PILOT", "format": "VFT reviewed scoring CSV"}
    mmn_ok = bool(mmn) and mmn.get("qc", {}).get("status") == "PASS"
    vft_ok = bool(vft) and vft.get("qc", {}).get("status") == "PASS"
    scoring_ok = bool(vft_scoring) and vft_scoring.get("status") == "SCORED"
    passed = mmn_ok and vft_ok and scoring_ok
    return {"workflow_schema": "BPLUS-ANALYSIS-1", "participant_id": participant_id,
            "age": age,
            "session_id": session_id, "sources": sources,
            "data_quality": {"score": 80 if passed else 0,
                             "band": "ACCEPTABLE" if passed else "INCOMPLETE",
                             "band_zh": "可接受" if passed else "数据不完整",
                             "components": {"mmn": mmn_ok, "vft_fnirs": vft_ok,
                                            "vft_scoring": scoring_ok},
                             "notes": [note for item in qc_items for note in item.get("notes", [])]},
            "features": features, "analysis": {"mmn": mmn, "vft": vft, "vft_scoring": vft_scoring},
            "review": {"decision": "PENDING", "reviewer": "", "note": ""}}


def review_package(package: dict[str, Any], *, reviewer: str, decision: str, note="") -> dict[str, Any]:
    if decision not in {"APPROVED", "REJECTED"} or not reviewer.strip():
        raise ValueError("审核必须填写审核人，并选择 APPROVED 或 REJECTED")
    copied = dict(package)
    copied["review"] = {"decision": decision, "reviewer": reviewer.strip(), "note": note.strip(),
                        "reviewed_at": datetime.now(timezone.utc).isoformat()}
    return copied


__all__ = ["analyze_mmn_epochs", "analyze_vft_hbo", "build_analysis_package", "read_vft_scoring",
           "review_package", "write_vft_scoring_template"]
