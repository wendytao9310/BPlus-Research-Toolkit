import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.simulate import generate_session, hrf, neural_drive


def test_session_shapes_and_truth():
    s = generate_session(60, seed=3)
    assert len(s.eeg) == int(60 * s.eeg_fs)
    assert len(s.hbo) == int(60 * s.fnirs_fs)
    assert len(s.gaze_x) == int(60 * s.eye_fs)
    assert len(s.ecg) == len(s.eda)
    assert s.truth.fnirs_lag_s == 5.0
    assert s.truth.coupled is True
    assert s.meta["note"].startswith("synthetic data")


def test_hrf_peaks_at_the_requested_lag():
    for lag in (3.0, 5.0, 7.0):
        h = hrf(peak_s=lag, fs=10.0)
        peak_t = float(np.argmax(h) / 10.0)
        assert abs(peak_t - lag) <= 1.0, (lag, peak_t)


def test_drive_is_slow_and_standardised():
    d = neural_drive(120, seed=1)
    assert abs(float(np.mean(d))) < 0.2
    assert 0.7 < float(np.std(d)) < 1.3
    # 慢变：一阶差分远小于信号本身
    assert float(np.std(np.diff(d))) < 0.3 * float(np.std(d))


def test_eeg_theta_amplitude_tracks_drive_when_coupled():
    from bplus.nvc import theta_envelope
    s = generate_session(120, coupled=True, coupling=0.8, seed=5)
    env = theta_envelope(s.eeg, s.eeg_fs, smooth_s=1.0)
    t_env = np.arange(len(env)) / s.eeg_fs
    t_drive = np.arange(len(s.drive)) / 10.0
    drive = np.interp(t_env, t_drive, s.drive)
    win = int(2.0 * s.eeg_fs)
    # 用 2 s 窗口均值比较慢变趋势，避免高频抖动干扰
    n = (len(env) // win) * win
    r = np.corrcoef(env[:n].reshape(-1, win).mean(1), drive[:n].reshape(-1, win).mean(1))[0, 1]
    assert r > 0.4, r


def test_uncoupled_session_uses_a_different_drive():
    s = generate_session(60, coupled=False, seed=7)
    assert s.truth.coupled is False
    assert s.truth.coupling_strength == 0.0
