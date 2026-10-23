import csv
import json

import numpy as np
import pytest

from bplus.analysis import (
    analyze_mmn_epochs,
    analyze_vft_hbo,
    build_analysis_package,
    read_vft_scoring,
    review_package,
)
from bplus.reports import generate_multimodal_report


def test_mmn_epoch_analysis_returns_negative_peak_and_qc():
    times = np.arange(-100.0, 501.0, 2.0)
    standard = np.zeros((30, 2, len(times)))
    deviant = np.zeros((20, 2, len(times)))
    peak = np.exp(-0.5 * ((times - 180.0) / 18.0) ** 2)
    deviant[:, 0, :] -= 2.0 * peak
    deviant[:, 1, :] -= 1.0 * peak
    result = analyze_mmn_epochs(standard, deviant, times, ["Fz", "Cz"])
    assert result["features"]["mmn_amplitude_abs_uv"] == pytest.approx(1.5, abs=0.1)
    assert result["features"]["mmn_latency_ms"] == pytest.approx(180.0, abs=3)
    assert result["qc"]["status"] == "PASS"


def test_vft_scoring_and_hbo_analysis(tmp_path):
    path = tmp_path / "vft_scoring.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["block", "prompt", "transcript", "valid_words", "repetitions", "intrusions", "reviewer"])
        writer.writeheader()
        writer.writerow({"block": 1, "prompt": "动物", "transcript": "猫 狗 猫 桌子", "valid_words": 2,
                         "repetitions": 1, "intrusions": 1, "reviewer": "R1"})
    scoring = read_vft_scoring(path)
    assert scoring["totals"]["valid_words"] == 2
    assert scoring["status"] == "SCORED"

    fs = 2.0
    hbo = np.zeros((2, 180))
    hbo[:, 60:120] = np.array([[0.3], [0.5]])
    result = analyze_vft_hbo(hbo, fs, task_windows=[(30, 30)], rest_windows=[(0, 30), (60, 30)])
    assert result["features"]["vft_hbo_delta_um"] == pytest.approx(0.4)
    assert result["qc"]["status"] == "PASS"


def test_report_requires_researcher_review(tmp_path):
    package = build_analysis_package("P01", "1", mmn={"features": {}, "qc": {"status": "PASS"}})
    source = tmp_path / "analysis.json"
    source.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="研究者审核"):
        generate_multimodal_report(source, tmp_path / "reports")

    reviewed = review_package(package, reviewer="Dr Li", decision="APPROVED", note="核对完成")
    source.write_text(json.dumps(reviewed, ensure_ascii=False), encoding="utf-8")
    paths = generate_multimodal_report(source, tmp_path / "reports")
    audit = json.loads(paths["state_profile"].read_text(encoding="utf-8"))
    assert audit["review"]["decision"] == "APPROVED"
    assert "不是诊断" in paths["html"].read_text(encoding="utf-8")
