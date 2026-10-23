"""Read-only CGX BrainVision import, EEG QC, optional MMN scoring and report package."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..analysis import analyze_mmn_epochs


EEG_NAMES = {"F7", "FP1", "FP2", "F8", "F3", "FZ", "F4", "C3", "CZ", "P8", "P7",
             "PZ", "P4", "T3", "P3", "O1", "O2", "C4", "T4"}
STANDARD_MARKERS = {"101", "11", "1", "MMN_STANDARD", "STANDARD", "SOUND_ONSET"}
DEVIANT_MARKERS = {"102", "12", "2", "MMN_DEVIANT", "DEVIANT", "TARGET_TONE"}
CGX_TASK_MARKERS = {
    "1": "声音实验开始",
    "2": "目标音出现",
    "3": "VFT任务开始",
    "4": "VFT任务结束",
    "5": "N-back开始",
    "6": "按下Enter",
    "7": "目标面孔出现",
    "8": "评分结束",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _marker_token(description: str) -> str:
    return re.split(r"[/ ]", str(description).strip())[-1].upper()


def _companion_files(header: Path) -> list[Path]:
    text = header.read_text(encoding="utf-8-sig", errors="replace")
    names = [header.name]
    for key in ("DataFile", "MarkerFile"):
        match = re.search(rf"^{key}=(.+)$", text, flags=re.MULTILINE)
        if match:
            names.append(match.group(1).strip())
    paths = [header.parent / name for name in names]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("BrainVision 数据不完整，缺少：" + "、".join(missing))
    return paths


def analyze_cgx_brainvision(header_path: str | Path, *, participant_id: str,
                            session_id: str, age: int | None = None) -> dict[str, Any]:
    """Load CGX BrainVision data locally without changing the source files."""
    try:
        import mne
    except ImportError as exc:
        raise RuntimeError("导入 CGX EEG 需要 MNE；请使用 BPlus 实验环境启动程序") from exc

    header = Path(header_path).resolve()
    files = _companion_files(header)
    raw = mne.io.read_raw_brainvision(header, preload=True, verbose="ERROR")
    channel_types = {}
    for name in raw.ch_names:
        upper = name.upper()
        if upper not in EEG_NAMES:
            channel_types[name] = "stim" if upper == "TRIGGER" else "misc"
    if channel_types:
        raw.set_channel_types(channel_types, verbose="ERROR")
    eeg = raw.copy().pick("eeg")
    if eeg.info["nchan"] < 4:
        raise ValueError("可识别 EEG 通道少于 4 个，无法执行自动分析")
    sfreq = float(eeg.info["sfreq"])
    duration = float(eeg.times[-1]) if len(eeg.times) else 0.0
    if sfreq < 100 or duration < 10:
        raise ValueError(f"EEG 记录过短或采样率异常：{duration:.1f}s / {sfreq:.1f}Hz")

    filtered = eeg.copy().filter(0.5, min(40.0, sfreq / 2 - 1), verbose="ERROR")
    data = filtered.get_data()
    robust_p2p_uv = (np.percentile(data, 99.5, axis=1) - np.percentile(data, 0.5, axis=1)) * 1e6
    std_uv = np.std(data, axis=1) * 1e6
    bad_channels = [name for name, p2p, std in zip(filtered.ch_names, robust_p2p_uv, std_uv)
                    if p2p > 500.0 or std < 0.2]
    usable_channels = [name for name in filtered.ch_names if name not in bad_channels]
    usable_ratio = len(usable_channels) / len(filtered.ch_names)

    epoch_samples = max(1, int(round(2.0 * sfreq)))
    n_epochs = data.shape[1] // epoch_samples
    epoch_p2p = []
    for index in range(n_epochs):
        segment = data[:, index * epoch_samples:(index + 1) * epoch_samples]
        epoch_p2p.append(float(np.max(np.ptp(segment, axis=1)) * 1e6))
    artifact_ratio = (sum(value > 500.0 for value in epoch_p2p) / len(epoch_p2p)) if epoch_p2p else 1.0

    psd = filtered.compute_psd(fmin=1.0, fmax=min(100.0, sfreq / 2 - 1), verbose="ERROR")
    spectra, freqs = psd.get_data(return_freqs=True)
    total = np.trapezoid(spectra, freqs, axis=1)
    def relative_band(low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs < high)
        band = np.trapezoid(spectra[:, mask], freqs[mask], axis=1)
        return float(np.nanmedian(np.divide(band, total, out=np.zeros_like(band), where=total > 0)))
    alpha_relative = relative_band(8.0, 13.0)
    theta_relative = relative_band(4.0, 8.0)
    alpha_mask = (freqs >= 7.0) & (freqs <= 13.0)
    median_spectrum = np.nanmedian(spectra, axis=0)
    iaf_hz = float(freqs[alpha_mask][np.nanargmax(median_spectrum[alpha_mask])])
    line_mask = (freqs >= 49.0) & (freqs <= 51.0)
    line = np.trapezoid(spectra[:, line_mask], freqs[line_mask], axis=1) if line_mask.any() else np.zeros_like(total)
    line_noise_ratio = float(np.nanmedian(np.divide(line, total, out=np.zeros_like(line), where=total > 0)))

    annotations = [str(item) for item in raw.annotations.description]
    counts = Counter(_marker_token(item) for item in annotations)
    marker_samples: dict[str, list[int]] = {}
    for onset, description in zip(raw.annotations.onset, raw.annotations.description):
        marker_samples.setdefault(_marker_token(description), []).append(int(round(float(onset) * sfreq)))
    standard_descriptions = [item for item in sorted(set(annotations)) if _marker_token(item) in STANDARD_MARKERS]
    deviant_descriptions = [item for item in sorted(set(annotations)) if _marker_token(item) in DEVIANT_MARKERS]
    mmn = None
    mmn_note = "未发现可无歧义识别的 MMN 标准/偏差事件码，未计算 MMN"
    if standard_descriptions and deviant_descriptions:
        events, event_id = mne.events_from_annotations(raw, verbose="ERROR")
        standard_ids = {event_id[item] for item in standard_descriptions}
        deviant_ids = {event_id[item] for item in deviant_descriptions}
        # MNE requires one integer per event label.  CGX exports can expose
        # several annotation spellings for the same logical marker, so remap
        # every accepted spelling to one stable synthetic event code.
        mmn_events = events.copy()
        mmn_events[np.isin(mmn_events[:, 2], list(standard_ids)), 2] = 9001
        mmn_events[np.isin(mmn_events[:, 2], list(deviant_ids)), 2] = 9002
        use = filtered.copy().drop_channels(bad_channels) if bad_channels else filtered
        epochs = mne.Epochs(use, mmn_events, event_id={"standard": 9001, "deviant": 9002},
                           tmin=-0.1, tmax=0.5, baseline=None, preload=True,
                           reject={"eeg": 500e-6}, verbose="ERROR")
        if len(epochs["standard"]) >= 10 and len(epochs["deviant"]) >= 10:
            times_ms = epochs.times * 1000.0
            mmn = analyze_mmn_epochs(epochs["standard"].get_data() * 1e6,
                                     epochs["deviant"].get_data() * 1e6,
                                     times_ms, epochs.ch_names)
            mmn_note = ("已按项目标记定义计算目标音（2）相对声音开始事件（1）的差异波；"
                        "该结果仅在标记1对应标准声音事件时可按经典MMN解释")
        else:
            mmn_note = "标准或偏差有效试次数不足，未计算 MMN"

    impedance = {}
    header_text = header.read_text(encoding="utf-8-sig", errors="replace")
    for match in re.finditer(r"^\d+\s+([A-Za-z0-9 ]+)\s+(\d+)\s+[-\d]+\s*$", header_text, re.MULTILINE):
        impedance[match.group(1).strip()] = int(match.group(2))
    impedance_ok = [name for name, value in impedance.items() if name.upper() in EEG_NAMES and value < 2500]
    impedance_warn = [name for name, value in impedance.items() if name.upper() in EEG_NAMES and value >= 2500]

    qc_pass = usable_ratio >= 0.80 and artifact_ratio <= 0.50 and duration >= 60.0
    score = 100.0 * (0.45 * usable_ratio + 0.35 * max(0.0, 1.0 - artifact_ratio) +
                     0.20 * max(0.0, 1.0 - min(1.0, line_noise_ratio * 20.0)))
    notes = [mmn_note]
    if bad_channels:
        notes.append("自动标记高振幅/平坦通道：" + "、".join(bad_channels))
    if impedance_warn:
        notes.append("采集时阻抗达到或超过 2500 kΩ：" + "、".join(impedance_warn))
    if not qc_pass:
        notes.append("EEG 自动质控未达到预设研究分析阈值；数值仅用于排查")
    features = {"eeg": {
        "usable_channel_ratio": usable_ratio, "artifact_ratio": artifact_ratio,
        "line_noise_ratio": line_noise_ratio, "global_alpha_relative_power": alpha_relative,
        "global_theta_relative_power": theta_relative, "global_alpha_peak_hz": iaf_hz,
    }, "rest": {}, "fnirs": {}, "vft": {}, "nback": {}, "nvc": {}, "emotion": {},
        "recovery": {}, "eye": {}, "physiology": {}, "clinical": {}}
    if mmn:
        features["eeg"].update(mmn["features"])

    task_analysis: dict[str, Any] = {}
    clean_names = [name for name in filtered.ch_names if name not in bad_channels]
    clean = filtered.copy().pick(clean_names).get_data()
    clean_name_lookup = {name.upper(): index for index, name in enumerate(clean_names)}

    def event_locked(codes: set[str], picks: tuple[str, ...], window: tuple[float, float],
                     epoch: tuple[float, float] = (-0.1, 0.8)) -> tuple[float | None, int]:
        indices = [clean_name_lookup[name.upper()] for name in picks if name.upper() in clean_name_lookup]
        samples = [sample for code in codes for sample in marker_samples.get(code, [])]
        if not indices or not samples:
            return None, 0
        start_offset, end_offset = int(epoch[0] * sfreq), int(epoch[1] * sfreq)
        base_a, base_b = int(-0.1 * sfreq), 0
        win_a, win_b = int(window[0] * sfreq), int(window[1] * sfreq)
        values = []
        for sample in samples:
            if sample + start_offset < 0 or sample + end_offset >= clean.shape[1]:
                continue
            baseline = clean[indices, sample + base_a:sample + base_b].mean()
            response = clean[indices, sample + win_a:sample + win_b].mean()
            values.append((response - baseline) * 1e6)
        return (float(np.mean(values)) if values else None), len(values)

    def band_power(segment: np.ndarray, low: float, high: float) -> float:
        if segment.shape[1] < sfreq:
            return float("nan")
        spectrum = np.abs(np.fft.rfft(segment, axis=1)) ** 2
        hz = np.fft.rfftfreq(segment.shape[1], 1.0 / sfreq)
        mask = (hz >= low) & (hz < high)
        return float(np.nanmean(spectrum[:, mask]))

    starts, ends = marker_samples.get("3", []), marker_samples.get("4", [])
    frontal = [clean_name_lookup[name.upper()] for name in ("Fp1", "Fp2", "F3", "Fz", "F4")
               if name.upper() in clean_name_lookup]
    theta_changes = []
    for start, end in zip(starts, ends):
        if end <= start or not frontal:
            continue
        length = end - start
        before = max(0, start - length)
        task_power = band_power(clean[frontal, start:end], 4.0, 8.0)
        base_power = band_power(clean[frontal, before:start], 4.0, 8.0)
        if task_power > 0 and base_power > 0:
            theta_changes.append(10.0 * np.log10(task_power / base_power))
    if theta_changes:
        features["eeg"]["vft_frontal_theta_change_db"] = float(np.mean(theta_changes))
        task_analysis["vft_eeg"] = {"qc": {"status": "PASS", "n_blocks": len(theta_changes),
                                               "markers": {"start": 3, "end": 4}}}

    nback_p3, n_enter = event_locked({"6"}, ("Cz", "Pz", "P3", "P4"), (0.25, 0.55))
    if nback_p3 is not None:
        features["eeg"]["nback_enter_locked_positive_uv"] = nback_p3
        task_analysis["nback_eeg"] = {"qc": {"status": "PASS" if n_enter >= 10 else "WARN",
                                                 "n_enter_events": n_enter, "marker": 6,
                                                 "locking": "response_locked"}}

    face_lpp, n_faces = event_locked({"7"}, ("Pz", "P3", "P4", "Cz"), (0.3, 0.8))
    if face_lpp is not None:
        features["eeg"]["emotion_target_face_lpp_uv"] = face_lpp
        task_analysis["emotion_eeg"] = {"qc": {"status": "PASS" if n_faces >= 5 else "WARN",
                                                   "n_target_faces": n_faces, "marker": 7}}
    source_records = [{"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
                      for path in files]
    analysis_qc = {
        "status": "PASS" if qc_pass else "QC_FAILED", "format": "BrainVision",
        "sampling_rate_hz": sfreq, "duration_s": duration,
        "n_recorded_channels": int(raw.info["nchan"]), "eeg_channels": filtered.ch_names,
        "usable_channels": usable_channels, "bad_channels": bad_channels,
        "usable_channel_ratio": usable_ratio, "artifact_ratio": artifact_ratio,
        "line_noise_ratio": line_noise_ratio, "marker_counts": dict(counts),
        "marker_dictionary": CGX_TASK_MARKERS,
        "alpha_relative_power": alpha_relative, "theta_relative_power": theta_relative,
        "alpha_peak_hz": iaf_hz,
        "impedance_below_2500_kohm": impedance_ok,
        "impedance_at_or_above_2500_kohm": impedance_warn, "notes": notes,
    }
    return {
        "workflow_schema": "BPLUS-ANALYSIS-1", "participant_id": participant_id,
        "session_id": session_id, "age": age,
        "sources": {"eeg": {"status": "VERIFIED", "format": "CGX BrainVision read-only import",
                            "files": source_records},
                    "fnirs": {"status": "MISSING"}, "eye": {"status": "MISSING"},
                    "behavior": {"status": "MISSING"}, "physiology": {"status": "MISSING"},
                    "clinical": {"status": "MISSING"}},
        "data_quality": {"score": round(score, 2),
                         "band": "ACCEPTABLE" if qc_pass else "INCOMPLETE",
                         "band_zh": "可接受" if qc_pass else "数据不足",
                         "components": {"eeg": analysis_qc}, "notes": notes},
        "features": features, "analysis": {"eeg_import": {"qc": analysis_qc}, "mmn": mmn,
                                                **task_analysis},
        "review": {"decision": "PENDING", "reviewer": "", "note": "",
                   "created_at": datetime.now(timezone.utc).isoformat()},
    }


def write_cgx_outputs(package: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {"package": output / "eeg_analysis_package.json", "qc": output / "eeg_qc.json"}
    paths["package"].write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["qc"].write_text(json.dumps(package["analysis"]["eeg_import"]["qc"],
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def analyze_cgx_bundle(folder: str | Path, *, participant_id: str,
                       session_id: str, age: int | None = None) -> dict[str, Any]:
    """Analyze every complete BrainVision recording in one EEG folder as one bundle."""
    root = Path(folder).resolve()
    headers = sorted(root.rglob("*.vhdr"))
    if not headers:
        raise FileNotFoundError("EEG 数据包中未找到 .vhdr 文件")
    packages, errors = [], []
    for header in headers:
        try:
            packages.append((header, analyze_cgx_brainvision(
                header, participant_id=participant_id, session_id=session_id, age=age)))
        except Exception as exc:
            errors.append({"file": str(header), "error": str(exc)})

    # Recover the common CGX export case where a complete binary was renamed
    # after export but the VHDR/VMRK still reference the old basename.  This is
    # only accepted when there is exactly one orphan binary and one compatible
    # missing-data header.  Raw files remain untouched; a temporary derivative
    # header is used solely for reading and full provenance is retained.
    referenced = set()
    for header in headers:
        match = re.search(r"^DataFile=(.+)$", header.read_text(encoding="utf-8-sig", errors="replace"), re.MULTILINE)
        if match:
            referenced.add((header.parent / match.group(1).strip()).resolve())
    orphans = [path.resolve() for path in root.rglob("*.eeg") if path.resolve() not in referenced]
    missing_headers = []
    for header in headers:
        text = header.read_text(encoding="utf-8-sig", errors="replace")
        data_match = re.search(r"^DataFile=(.+)$", text, re.MULTILINE)
        if data_match and not (header.parent / data_match.group(1).strip()).exists():
            missing_headers.append(header)
    if len(orphans) == 1 and len(missing_headers) == 1:
        header, orphan = missing_headers[0], orphans[0]
        text = header.read_text(encoding="utf-8-sig", errors="replace")
        nchan = int(re.search(r"^NumberOfChannels=(\d+)$", text, re.MULTILINE).group(1))
        points = int(re.search(r"^DataPoints=(\d+)$", text, re.MULTILINE).group(1))
        expected = nchan * points * 4
        if expected and abs(orphan.stat().st_size - expected) / expected <= 0.02:
            marker = header.parent / re.search(r"^MarkerFile=(.+)$", text, re.MULTILINE).group(1).strip()
            if marker.exists():
                with tempfile.TemporaryDirectory(prefix="bplus-cgx-repair-") as tmp:
                    work = Path(tmp)
                    repaired_marker = work / marker.name
                    repaired_marker.write_text(re.sub(r"^DataFile=.+$", f"DataFile={orphan}",
                                                      marker.read_text(encoding="utf-8-sig", errors="replace"),
                                                      flags=re.MULTILINE), encoding="utf-8")
                    repaired_header = work / header.name
                    repaired = re.sub(r"^DataFile=.+$", f"DataFile={orphan}", text, flags=re.MULTILINE)
                    repaired = re.sub(r"^MarkerFile=.+$", f"MarkerFile={repaired_marker.name}", repaired,
                                      flags=re.MULTILINE)
                    repaired_header.write_text(repaired, encoding="utf-8")
                    package = analyze_cgx_brainvision(repaired_header, participant_id=participant_id,
                                                      session_id=session_id, age=age)
                original_sources = [header, marker, orphan]
                package["sources"]["eeg"]["files"] = [
                    {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
                    for path in original_sources]
                package["analysis"]["eeg_import"]["qc"]["derived_filename_repair"] = {
                    "status": "VERIFIED_BY_LAYOUT", "header": str(header), "binary": str(orphan),
                    "expected_bytes": expected, "actual_bytes": orphan.stat().st_size,
                    "size_difference_ratio": abs(orphan.stat().st_size - expected) / expected,
                }
                package["data_quality"]["notes"].append(
                    f"只读恢复文件名关联：{header.name} → {orphan.name}（原始文件未修改）")
                if "rest" in orphan.name.lower():
                    eeg_features = package["features"]["eeg"]
                    package["features"]["rest"] = {
                        "alpha_relative_power": eeg_features["global_alpha_relative_power"],
                        "theta_relative_power": eeg_features["global_theta_relative_power"],
                        "iaf_hz": eeg_features["global_alpha_peak_hz"],
                    }
                    package["analysis"]["rest"] = {"qc": {"status": package["analysis"]["eeg_import"]["qc"]["status"],
                                                               "source": orphan.name}}
                packages.append((header, package))
                errors = [item for item in errors if Path(item["file"]) != header]
    if not packages:
        details = "；".join(f"{Path(item['file']).name}: {item['error']}" for item in errors)
        raise ValueError("EEG 数据包没有可分析的完整记录：" + details)

    def qc_of(package):
        return package["analysis"]["eeg_import"]["qc"]

    # Prefer an explicit MMN result; otherwise use the longest recording for the
    # report-level EEG QC while retaining every run in the researcher appendix.
    primary = next((item for item in packages if item[1]["analysis"].get("mmn")), None)
    if primary is None:
        primary = max(packages, key=lambda item: qc_of(item[1])["duration_s"])
    _, selected = primary
    recording_qc = [{"header": str(path), **qc_of(package)} for path, package in packages]
    scores = [float(package["data_quality"]["score"]) for _, package in packages]
    all_files = []
    for _, package in packages:
        all_files.extend(package["sources"]["eeg"].get("files", []))
    notes = list(selected["data_quality"].get("notes", []))
    notes.append(f"EEG 大数据包共识别 {len(headers)} 组头文件，成功分析 {len(packages)} 组")
    if errors:
        notes.append("未纳入的不完整记录：" + "；".join(
            f"{Path(item['file']).name}（{item['error']}）" for item in errors))
    selected["sources"]["eeg"] = {
        "status": "VERIFIED", "format": "CGX BrainVision folder batch import",
        "root": str(root), "files": all_files,
    }
    selected["data_quality"]["score"] = round(sum(scores) / len(scores), 2)
    selected["data_quality"]["notes"] = notes
    selected["data_quality"]["components"]["eeg_bundle"] = {
        "headers_found": len(headers), "recordings_analyzed": len(packages),
        "recordings_rejected": len(errors), "primary_recording": str(primary[0]),
    }
    selected["analysis"]["eeg_recordings"] = recording_qc
    selected["analysis"]["eeg_bundle_errors"] = errors
    rest_package = next((package for _, package in packages if package.get("features", {}).get("rest")), None)
    if rest_package:
        selected["features"]["rest"] = rest_package["features"]["rest"]
        selected["analysis"]["rest"] = rest_package["analysis"]["rest"]
    selected["review"] = {"decision": "PENDING", "reviewer": "", "note": ""}
    return selected


__all__ = ["analyze_cgx_brainvision", "analyze_cgx_bundle", "write_cgx_outputs"]
