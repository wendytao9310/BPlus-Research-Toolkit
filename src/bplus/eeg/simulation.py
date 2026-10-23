"""Deterministic MMN software-loop simulation.

This module validates BPlus' event, epoch, analysis, QC and report plumbing. It
does not emulate amplifier physics and its output must never be treated as a
participant measurement.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..analysis import analyze_mmn_epochs, review_package
from ..reports import generate_multimodal_report


def read_curry_metadata(path: str | Path) -> tuple[float, list[str], dict[str, Any]]:
    """Read CURRY acquisition metadata without preloading or modifying raw data."""
    import mne

    source = Path(path)
    raw = mne.io.read_raw_curry(source, preload=False, verbose="ERROR")
    names = [name for name, kind in zip(raw.ch_names, raw.get_channel_types()) if kind == "eeg"]
    metadata = {"reference_file": str(source.resolve()), "read_mode": "metadata_only_read_only",
                "sfreq_hz": float(raw.info["sfreq"]), "n_times": int(raw.n_times),
                "duration_s": float(raw.n_times / raw.info["sfreq"]),
                "n_eeg_channels": len(names), "all_channel_names": raw.ch_names}
    return float(raw.info["sfreq"]), names, metadata


def _channel_gain(name: str) -> float:
    upper = name.upper()
    if upper in {"FZ", "CZ"}:
        return 1.0
    if upper.startswith("F") or upper.startswith("C"):
        return 0.55
    return 0.20


def _epochs(n_epochs: int, times_ms: np.ndarray, channel_names: list[str], *,
            amplitude_uv: float, latency_ms: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 2.2, (n_epochs, len(channel_names), len(times_ms)))
    # Add low-frequency background without phase-locking it across trials.
    for epoch in range(n_epochs):
        phase = rng.uniform(0, 2 * np.pi, len(channel_names))[:, None]
        data[epoch] += 1.1 * np.sin(2 * np.pi * 6.3 * times_ms[None, :] / 1000.0 + phase)
    peak = np.exp(-0.5 * ((times_ms - latency_ms) / 25.5) ** 2)
    gains = np.asarray([_channel_gain(name) for name in channel_names])
    data += amplitude_uv * gains[None, :, None] * peak[None, None, :]
    return data.astype(np.float32)


def _events(n_standard: int, n_deviant: int, sfreq: float) -> list[dict[str, Any]]:
    labels = ["deviant" if (index + 1) % 5 == 0 else "standard"
              for index in range(n_standard + n_deviant)]
    # Exact requested counts, even if a caller changes the default 80/20 ratio.
    labels = ["standard"] * n_standard + ["deviant"] * n_deviant
    rng = np.random.default_rng(20261013)
    rng.shuffle(labels)
    rows = [{"event_index": 0, "onset_s": 1.0, "sample": int(sfreq),
             "code": 100, "label": "mmn_start"}]
    for index, label in enumerate(labels, 1):
        onset = 2.0 + index * 1.5
        rows.append({"event_index": index, "onset_s": onset,
                     "sample": int(round(onset * sfreq)),
                     "code": 102 if label == "deviant" else 101, "label": label})
    end_onset = 3.0 + len(labels) * 1.5
    rows.append({"event_index": len(labels) + 1, "onset_s": end_onset,
                 "sample": int(round(end_onset * sfreq)), "code": 109, "label": "mmn_end"})
    return rows


def run_mmn_simulation(output_dir: str | Path, *, participant_id: str = "SIM-EEG001",
                       session_id: str = "1", sfreq: float = 1000.0,
                       channel_names: list[str] | None = None,
                       source_metadata: dict[str, Any] | None = None,
                       n_standard: int = 160, n_deviant: int = 40,
                       seed: int = 20261013) -> dict[str, Path]:
    """Generate complete simulated MMN data and exercise the report pipeline."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    names = list(channel_names or ["Fz", "Cz", "F3", "F4", "C3", "C4", "Pz", "Oz"])
    canonical = {name.upper(): name for name in names}
    for required in ("FZ", "CZ"):
        if required not in canonical:
            names.append(required.title())
    times = np.arange(-100.0, 501.0, 1000.0 / float(sfreq))
    standard = _epochs(n_standard, times, names, amplitude_uv=-0.6, latency_ms=200.0, seed=seed)
    deviant = _epochs(n_deviant, times, names, amplitude_uv=-3.5, latency_ms=200.0, seed=seed + 1)
    result = analyze_mmn_epochs(standard, deviant, times, names, roi=(canonical.get("FZ", "Fz"),
                                                                     canonical.get("CZ", "Cz")))
    events = _events(n_standard, n_deviant, sfreq)

    event_path = output / "events.csv"
    with event_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(events[0]))
        writer.writeheader(); writer.writerows(events)
    epoch_path = output / "mmn_preprocessed_epochs.npz"
    np.savez_compressed(epoch_path, standard_epochs_uv=standard, deviant_epochs_uv=deviant,
                        times_ms=times, channel_names=np.asarray(names))
    truth = {"scope": "SOFTWARE_SIMULATION_ONLY", "not_real_participant_data": True,
             "sfreq_hz": sfreq, "n_channels": len(names), "n_standard": n_standard,
             "n_deviant": n_deviant, "mmn_difference_amplitude_uv": -2.9,
             "mmn_latency_ms": 200.0, "seed": seed,
             "source_metadata": source_metadata or {}}
    truth_path = output / "simulation_truth.json"
    truth_path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

    features = {"eeg": result["features"], "fnirs": {}, "vft": {}, "nback": {},
                "nvc": {}, "emotion": {}, "recovery": {}, "eye": {}, "clinical": {}}
    package = {
        "workflow_schema": "BPLUS-ANALYSIS-1", "participant_id": participant_id,
        "session_id": session_id,
        "sources": {"eeg": {"status": "SIMULATED", "format": "BPlus synthetic MMN epochs",
                              "file": str(epoch_path)},
                    **{name: {"status": "MISSING"} for name in ("fnirs", "eye", "behavior", "clinical")}},
        "data_quality": {"score": 80.0, "band": "ACCEPTABLE", "band_zh": "软件验证通过",
                         "components": {"event_sequence": True, "mmn_epochs": True,
                                        "mmn_analysis": result["qc"]["status"] == "PASS"},
                         "notes": ["仅用于软件闭环验证；不代表设备质量或被试脑功能。"]},
        "features": features, "analysis": {"mmn": result}, "simulation_truth": truth,
        "review": {"decision": "PENDING", "reviewer": "", "note": ""},
    }
    package = review_package(package, reviewer="BPlus software validation", decision="APPROVED",
                             note="仅批准软件模拟闭环；不得作为正式被试报告。")
    package_path = output / "analysis_package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    report_paths = generate_multimodal_report(package_path, output / "report")
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "PASS" if result["qc"]["status"] == "PASS" else "FAIL",
                "scope": "SOFTWARE_SIMULATION_ONLY", "analysis": result,
                "files": {"events": str(event_path), "epochs": str(epoch_path),
                          "truth": str(truth_path), "package": str(package_path),
                          "report_html": str(report_paths["html"])}}
    manifest_path = output / "validation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"events": event_path, "epochs": epoch_path, "truth": truth_path,
            "package": package_path, "manifest": manifest_path, **report_paths}


__all__ = ["read_curry_metadata", "run_mmn_simulation"]
