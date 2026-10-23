import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.features import (count_scr, extract_mmn, glm_task_beta, hrv_sdnn, line_noise_ratio,
                            motion_artifact_ratio, scalp_coupling_index)
from bplus.simulate import generate_session


def _mmn_events(n_dev=120, n_std=360, step=3.0, start=10.0):
    dev = [start + step * i for i in range(n_dev)]
    std = [start + step * i + j for i in range(n_dev) for j in (1.0, 2.0, 0.5)]
    return {"deviant_onsets_s": dev, "standard_onsets_s": std[:n_std]}


def test_mmn_amplitude_and_latency_are_recovered():
    ev = _mmn_events()
    s = generate_session(500, mmn_events=ev, group="healthy_like", seed=3)
    m = extract_mmn(s.eeg, s.eeg_fs, deviant_onsets_s=ev["deviant_onsets_s"],
                    standard_onsets_s=ev["standard_onsets_s"])
    assert abs(m["mmn_amplitude_uv"] - s.truth.mmn_amplitude_uv) < 0.8
    assert abs(m["mmn_latency_ms"] - s.truth.mmn_latency_ms) < 40
    assert m["n_deviants"] > 100 and m["n_standards"] > 200


def test_mmn_group_contrast_matches_truth():
    """健康样 vs 抑郁样：差异波幅度差 1.9 μV（对标锚论文 P001 的效应量）。"""
    ev = _mmn_events()
    out = {}
    for group in ("healthy_like", "depressed_like"):
        s = generate_session(500, mmn_events=ev, group=group, seed=3)
        out[group] = extract_mmn(s.eeg, s.eeg_fs, deviant_onsets_s=ev["deviant_onsets_s"],
                                 standard_onsets_s=ev["standard_onsets_s"])["mmn_amplitude_uv"]
    assert out["healthy_like"] < out["depressed_like"] - 0.5      # 更负 = 更强 MMN


def test_glm_task_beta_recovers_the_induced_response():
    s = generate_session(300, task_blocks=[(100, 60, 0.4)], task_amp=0.4, seed=4)
    g = glm_task_beta(s.hbo, s.fnirs_fs, task_blocks=[(100, 60, 0.4)])
    assert 0.15 < g["beta_um"] < 0.9                              # 真值 0.4 μM


def test_sci_is_high_for_shared_wavelength_signal():
    s = generate_session(120, seed=5)
    sci = scalp_coupling_index(s.raw_760, s.raw_850, s.fnirs_fs)
    assert 0.6 < sci <= 1.0


def test_physiology_features_are_in_expected_ranges():
    s = generate_session(300, seed=6)
    assert 5.0 < hrv_sdnn(s.beats) < 80.0
    assert 4 <= count_scr(s.eda, s.eeg_fs) <= 14                  # 真值 8


def test_qc_metrics_are_low_for_a_clean_synthetic_recording():
    s = generate_session(60, seed=7)
    assert motion_artifact_ratio(s.hbo) < 0.05
    assert 0.0 <= line_noise_ratio(s.eeg, s.eeg_fs) <= 1.0
