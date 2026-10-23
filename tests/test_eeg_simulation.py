import csv
import json

import numpy as np
import pytest

from bplus.eeg import run_mmn_simulation


def test_complete_mmn_simulation_recovers_truth_and_marks_report(tmp_path):
    paths = run_mmn_simulation(tmp_path / "sim", channel_names=["Fz", "Cz", "Pz"])
    package = json.loads(paths["package"].read_text(encoding="utf-8"))
    result = package["analysis"]["mmn"]
    assert result["qc"]["status"] == "PASS"
    assert result["qc"]["n_standard"] == 160
    assert result["qc"]["n_deviant"] == 40
    assert result["features"]["mmn_amplitude_uv"] == pytest.approx(-2.9, abs=0.8)
    assert result["features"]["mmn_latency_ms"] == pytest.approx(200.0, abs=20.0)
    assert package["sources"]["eeg"]["status"] == "SIMULATED"
    assert package["simulation_truth"]["not_real_participant_data"] is True
    assert package["review"]["decision"] == "APPROVED"

    with paths["events"].open(encoding="utf-8-sig") as handle:
        events = list(csv.DictReader(handle))
    assert [row["code"] for row in events].count("101") == 160
    assert [row["code"] for row in events].count("102") == 40
    assert events[0]["code"] == "100" and events[-1]["code"] == "109"

    arrays = np.load(paths["epochs"])
    assert arrays["standard_epochs_uv"].shape == (160, 3, 601)
    html = paths["html"].read_text(encoding="utf-8")
    assert "Software Simulation Validation" in html
    assert "must not be used as a real participant result" in html
