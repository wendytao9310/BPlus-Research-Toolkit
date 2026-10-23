import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.qc import compute_dq, score_eeg, score_fnirs, score_physiology, score_synchronization
from scripts.qc_from_exports import build_report, compute_eeg_qc, load_fnirs, make_demo_exports


def test_missing_physiology_renormalises_weights_instead_of_zeroing():
    eeg = score_eeg(usable_channel_ratio=0.95)
    fnirs = score_fnirs(sci=0.9, channel_quality=0.95)
    sync = score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3)
    with_physio = compute_dq(eeg=eeg, fnirs=fnirs, epoch=sync, sync=sync,
                             physiology=score_physiology(valid_segment_ratio=0.95, hrv_sdnn_ms=40, scr_events=3))
    without = compute_dq(eeg=eeg, fnirs=fnirs, epoch=sync, sync=sync, physiology=None)
    assert without.components["missing"] == ["physiology"]
    assert abs(without.score - with_physio.score) < 5          # 缺失时不应假性崩盘
    assert any("重新归一化" in n for n in without.notes)


def test_demo_exports_produce_a_usable_dq_report(tmp_path):
    eeg_csv, fnirs_csv = make_demo_exports(tmp_path)
    data, fs, _ = __import__("scripts.qc_from_exports", fromlist=["load_eeg"]).load_eeg(eeg_csv)
    mapping = {"sampling_interval_ms": 75, "time_column": "Time(s)", "marker_column": "Mark",
               "hbo_columns": ["CH1 Oxy-Hb", "CH2 Oxy-Hb"], "hbr_columns": ["CH1 Deoxy-Hb"],
               "raw_760_columns": ["CH1 raw760"], "raw_850_columns": ["CH1 raw850"]}
    fnirs = load_fnirs(fnirs_csv, mapping)
    assert fnirs["hbo"].shape[0] == fnirs["time"].shape[0] > 100
    sci = __import__("bplus.features", fromlist=["scalp_coupling_index"]).scalp_coupling_index(
        fnirs["raw_760"], fnirs["raw_850"], 1000 / 75)
    assert 0.5 < sci <= 1.0
    report, html = build_report(
        {"eeg_qc": compute_eeg_qc(data, fs), "fnirs_qc": {"sci": sci, "channel_quality": 1 - 0.01,
                                                          "motion_artifact_ratio": 0.01, "baseline_drift": 0.1},
         "epoch": {"valid_ratio": 0.95, "n_per_condition": 40}, "physiology": None},
        {"verdict": "PASS", "counts": {"eeg": 10, "fnirs": 10}, "missing_codes": [],
         "offset_ms": 12.0, "jitter_sd_ms": 8.0})
    assert report["dq"]["band"] in ("GOOD", "ACCEPTABLE")
    assert "dq" in report and "subscores" in json.loads(json.dumps(report, default=str))
    assert "<html" in html


def test_unfilled_lightnirs_mapping_fails_loudly(tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("Time,CH1\n0,1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="列映射"):
        load_fnirs(csv_path, {"time_column": None, "hbo_columns": []})


def test_wrong_column_name_fails_with_the_real_header(tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("Time,CH1 Oxy-Hb\n0,1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="找不到"):
        load_fnirs(csv_path, {"time_column": "Time", "hbo_columns": ["CH9 Oxy-Hb"]})
