"""QC-gated 15-30-15 interview analysis and auditable output writer."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .shimadzu import FNIRSRaw


def _safe_stats(values: list[float]) -> dict[str, float | None]:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    if not len(data):
        return {"mean": None, "median": None, "sd": None, "iqr": None}
    return {"mean": float(np.mean(data)), "median": float(np.median(data)),
            "sd": float(np.std(data)), "iqr": float(np.percentile(data, 75) - np.percentile(data, 25))}


def analyze_interview(raw: FNIRSRaw, *, hemodynamic_delay_s: float = 5.0,
                      min_valid_block_ratio: float = 0.8) -> dict[str, Any]:
    usable = set(raw.qc["channels"]["usable_indices"])
    block_rows = []
    for block in raw.blocks:
        row: dict[str, Any] = {"index": block.index, "qc_status": block.qc_status, "channels": {}}
        delay = round(hemodynamic_delay_s * raw.sampling_rate)
        for channel in range(raw.n_channels):
            pre = slice(block.pre_start, block.interview_start)
            task = slice(min(block.interview_start + delay, block.interview_end), block.interview_end)
            post = slice(min(block.interview_end + delay, block.post_end + 1), block.post_end + 1)
            metrics = {}
            for name, signal in (("hbo", raw.hbo[:, channel]), ("hbr", raw.hbr[:, channel]),
                                 ("hbt", raw.hbt[:, channel])):
                pre_mean = float(np.nanmean(signal[pre])); task_mean = float(np.nanmean(signal[task]))
                post_mean = float(np.nanmean(signal[post]))
                metrics[name] = {"pre": pre_mean, "interview": task_mean, "post": post_mean,
                                 "interview_minus_pre": task_mean - pre_mean,
                                 "post_minus_pre": post_mean - pre_mean}
            row["channels"][str(channel + 1)] = metrics
        if block.qc_status != "PASS" or not usable:
            row["qc_status"] = "FAIL"
        block_rows.append(row)

    valid = [row for row in block_rows if row["qc_status"] == "PASS"]
    required = max(1, int(np.ceil(len(raw.blocks) * min_valid_block_ratio)))
    analysis_ok = raw.qc["status"] != "FAIL" and len(valid) >= required and bool(usable)
    channel_metrics: dict[str, Any] = {}
    if analysis_ok:
        for channel in sorted(usable):
            channel_metrics[str(channel)] = {}
            for chromophore in ("hbo", "hbr", "hbt"):
                values = [row["channels"][str(channel)][chromophore]["interview_minus_pre"] for row in valid]
                channel_metrics[str(channel)][f"{chromophore}_interview_minus_pre"] = _safe_stats(values)

    # Validated probe layout order: first 10 channels right probe, last 10 left probe.
    # We intentionally do not infer specific cortical gyri from this ordering.
    def roi_values(channels: list[int], chromophore: str, metric: str) -> list[float]:
        values = []
        for row in valid:
            current = [row["channels"][str(ch)][chromophore][metric] for ch in channels if ch in usable]
            if current:
                values.append(float(np.nanmean(current)))
        return values

    right_channels = list(range(1, 11)); left_channels = list(range(11, 21))
    roi: dict[str, Any] = {}
    if analysis_ok:
        for name, channels in (("right_probe", right_channels), ("left_probe", left_channels)):
            roi[name] = {f"{chrom}_interview_minus_pre": _safe_stats(roi_values(channels, chrom, "interview_minus_pre"))
                         for chrom in ("hbo", "hbr", "hbt")}
            roi[name]["hbo_post_minus_pre"] = _safe_stats(roi_values(channels, "hbo", "post_minus_pre"))
        left = roi["left_probe"]["hbo_interview_minus_pre"]["mean"]
        right = roi["right_probe"]["hbo_interview_minus_pre"]["mean"]
        roi["left_right_hbo_difference"] = None if left is None or right is None else left - right
    status = "PASS" if analysis_ok and raw.qc["status"] == "PASS" else ("WARN" if analysis_ok else "DATA_INSUFFICIENT")
    features = {
        "interview_left_probe_hbo_response": roi.get("left_probe", {}).get("hbo_interview_minus_pre", {}).get("mean"),
        "interview_right_probe_hbo_response": roi.get("right_probe", {}).get("hbo_interview_minus_pre", {}).get("mean"),
        "interview_left_right_hbo_difference": roi.get("left_right_hbo_difference"),
        "interview_hbr_response": _safe_stats(
            roi_values(sorted(usable), "hbr", "interview_minus_pre"))["mean"] if analysis_ok else None,
        "interview_post_task_recovery": _safe_stats(
            roi_values(sorted(usable), "hbo", "post_minus_pre"))["mean"] if analysis_ok else None,
        "interview_valid_blocks": len(valid),
        "interview_usable_channels": len(usable),
    }
    return {"device": "Shimadzu", "modality": "fNIRS", "status": status,
            "recording": {"sampling_rate": raw.sampling_rate, "duration": raw.duration,
                          "n_samples": raw.n_samples, "n_channels": raw.n_channels},
            "qc": raw.qc, "parameters": {"hemodynamic_delay_s": hemodynamic_delay_s,
                                           "min_valid_block_ratio": min_valid_block_ratio},
            "blocks": block_rows, "channel_metrics": channel_metrics, "roi_metrics": roi,
            "features": features}


def write_analysis_outputs(raw: FNIRSRaw, analysis: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    output = Path(out_dir); output.mkdir(parents=True, exist_ok=True)
    paths = {name: output / filename for name, filename in {
        "manifest": "import_manifest.json", "qc": "qc.json", "analysis": "analysis_results.json",
        "report_payload": "report_payload.json"}.items()}
    manifest = {"manufacturer": raw.manufacturer, "device_model": raw.device_model,
                "protocol_name": raw.metadata.get("timepath", raw.metadata.get("profile")),
                "subject_id": raw.subject_id, "session_id": raw.session_id,
                "source_files": raw.qc["files"], "read_only_import": True}
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["qc"].write_text(json.dumps(raw.qc, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["analysis"].write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["report_payload"].write_text(json.dumps({"fnirs": analysis["features"], "qc": raw.qc,
                                                   "status": analysis["status"]},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def export_report_pdf(html_path: str | Path, pdf_path: str | Path) -> Path:
    """Print a local, already-rendered report to PDF without network access."""
    html = Path(html_path).resolve(); pdf = Path(pdf_path).resolve()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    browser = next((path for path in candidates if path.exists()), None)
    if browser is None:
        resolved = shutil.which("google-chrome") or shutil.which("chromium")
        browser = Path(resolved) if resolved else None
    if browser is None:
        raise RuntimeError("未找到可用于生成 PDF 的 Chrome/Chromium；HTML 报告已保留")
    command = [str(browser), "--headless", "--disable-gpu", "--no-pdf-header-footer",
               f"--print-to-pdf={pdf}", html.as_uri()]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if completed.returncode or not pdf.exists() or pdf.stat().st_size == 0:
        raise RuntimeError(completed.stderr.strip() or "PDF 生成失败")
    return pdf


def build_fnirs_analysis_package(raw: FNIRSRaw, analysis: dict[str, Any], *, participant_id: str,
                                 session_id: str, age: int | None = None) -> dict[str, Any]:
    """Map a QC-gated Shimadzu result into the existing BPlus report contract."""
    qc_pass = analysis["status"] in {"PASS", "WARN"}
    score = 0.0
    if qc_pass:
        channel_ratio = raw.qc["channels"]["usable"] / raw.n_channels
        expected = raw.qc["task"]["expected_blocks"] or max(1, len(raw.blocks))
        block_ratio = raw.qc["task"]["valid_blocks"] / expected
        optical_ratio = 1.0 - raw.qc["optical"]["invalid_optical_ratio"]
        score = round(100 * (0.4 * channel_ratio + 0.4 * block_ratio + 0.2 * optical_ratio), 2)
    features = {"eeg": {}, "fnirs": dict(analysis["features"]), "vft": {}, "nback": {},
                "nvc": {}, "emotion": {}, "recovery": {}, "eye": {}, "clinical": {}}
    return {
        "workflow_schema": "BPLUS-ANALYSIS-1", "participant_id": participant_id,
        "session_id": session_id, "age": age,
        "sources": {"eeg": {"status": "MISSING"},
                    "fnirs": {"status": "VERIFIED", "format": "Shimadzu OMM read-only import",
                              "session": raw.source_files["omm"].stem},
                    "eye": {"status": "MISSING"}, "behavior": {"status": "MISSING"},
                    "clinical": {"status": "MISSING"}},
        "data_quality": {"score": score, "band": "ACCEPTABLE" if qc_pass else "INCOMPLETE",
                         "band_zh": "可接受" if qc_pass else "数据不足",
                         "components": {"fnirs_file_integrity": True,
                                        "fnirs_usable_channels": raw.qc["channels"]["usable"],
                                        "fnirs_valid_blocks": raw.qc["task"]["valid_blocks"]},
                         "notes": list(raw.qc.get("warnings", []))},
        "features": features, "analysis": {"interview": {"features": analysis["features"],
                                                             "parameters": analysis.get("parameters", {}),
                                                             "qc": {"status": analysis["status"],
                                                                    **raw.qc}}},
        "review": {"decision": "PENDING", "reviewer": "", "note": "",
                   "created_at": datetime.now(timezone.utc).isoformat()},
    }
